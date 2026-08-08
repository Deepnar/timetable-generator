"""FastAPI entry point for the Enterprise Timetable Management System."""
import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from jose import jwt
from sqlalchemy import text

from .config import settings as app_settings
from .database import engine, SessionLocal
from . import models
from .models.audit import AuditLog
from .utils.auth import authenticate_token
from .router import (
    auth,
    rooms,
    groups,
    faculty,
    subjects,
    room_blackout,
    faculty_availibility,
    profiles,
    constraints,
    generate,
    instances,
    import_csv,
    history,
    reset,
    export,
    settings,
    assignments,
    audit,
)
from .services.settings_service import get_settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("timetable")

_MUTATING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Ensure the college-settings singleton row exists on startup."""
    db = SessionLocal()
    try:
        get_settings(db)
    finally:
        db.close()
    yield


app = FastAPI(title="Timetable Generator API", lifespan=lifespan)


# ── Auth: every route requires a valid admin JWT except /health and /auth/* ──
# One middleware instead of a dependency on every route guarantees a new
# router/endpoint cannot accidentally be left public. Registered before the
# observability middleware so rejected requests still get logged/audited, and
# CORS (added last) still wraps everything.
_AUTH_EXEMPT_PATHS = {"/health"}


def _auth_response(status_code: int, detail: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"detail": detail},
        headers={"WWW-Authenticate": "Bearer"},
    )


@app.middleware("http")
async def require_auth(request: Request, call_next):
    path = request.url.path.rstrip("/") or "/"
    if path in _AUTH_EXEMPT_PATHS or path.startswith("/auth/"):
        return await call_next(request)

    header = request.headers.get("authorization", "")
    if not header.lower().startswith("bearer "):
        return _auth_response(
            status.HTTP_401_UNAUTHORIZED, "Could not validate credentials"
        )

    db = SessionLocal()
    try:
        admin = authenticate_token(header[7:].strip(), db)
    finally:
        db.close()
    if admin is None:
        return _auth_response(
            status.HTTP_401_UNAUTHORIZED, "Could not validate credentials"
        )

    return await call_next(request)


# ── Observability: request logging, global error handling, audit ──────
def _admin_id_from_request(request: Request) -> int | None:
    """Best-effort admin id from the bearer token (for the audit trail)."""
    header = request.headers.get("authorization", "")
    if not header.lower().startswith("bearer "):
        return None
    try:
        payload = jwt.decode(
            header[7:], app_settings.SECRET_KEY, algorithms=[app_settings.ALGORITHM]
        )
        return payload.get("admin_id")
    except Exception:
        return None


def _write_audit(request: Request, status_code: int, request_id: str) -> None:
    db = SessionLocal()
    try:
        db.add(AuditLog(
            method=request.method,
            path=request.url.path,
            status_code=status_code,
            admin_id=_admin_id_from_request(request),
            request_id=request_id,
        ))
        db.commit()
    except Exception:  # never let auditing break the request
        db.rollback()
        logger.exception("Failed to write audit log")
    finally:
        db.close()


@app.middleware("http")
async def observability(request: Request, call_next):
    request_id = uuid.uuid4().hex[:8]
    start = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        logger.exception(
            "Unhandled error: %s %s [%s]",
            request.method, request.url.path, request_id,
        )
        response = JSONResponse(
            status_code=500,
            content={"detail": "Internal server error", "request_id": request_id},
        )
    duration_ms = (time.perf_counter() - start) * 1000
    response.headers["X-Request-ID"] = request_id
    logger.info(
        "%s %s -> %d (%.1f ms) [%s]",
        request.method, request.url.path, response.status_code, duration_ms, request_id,
    )
    if request.method in _MUTATING_METHODS:
        _write_audit(request, response.status_code, request_id)
    return response


# CORS is registered last so it wraps everything (headers on error responses too).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(auth.router)
app.include_router(rooms.router)
app.include_router(faculty.router)
app.include_router(groups.router)
app.include_router(subjects.router)
app.include_router(room_blackout.router)
app.include_router(faculty_availibility.router)
app.include_router(profiles.router)
app.include_router(constraints.router)
app.include_router(generate.router)
app.include_router(instances.router)
app.include_router(import_csv.router)
app.include_router(history.router)
app.include_router(reset.router)
app.include_router(export.router)
app.include_router(settings.router)
app.include_router(assignments.router)
app.include_router(audit.router)


@app.get("/health", tags=["Health"])
def health() -> dict:
    """Liveness + DB reachability check used by deployment monitors."""
    db_ok = True
    db_error: str | None = None
    db = SessionLocal()
    try:
        db.execute(text("SELECT 1"))
    except Exception as exc:  # pragma: no cover - exercised in prod
        db_ok = False
        db_error = str(exc)
    finally:
        db.close()
    return {
        "status": "ok" if db_ok else "degraded",
        "db": "connected" if db_ok else "down",
        "db_error": db_error,
    }
