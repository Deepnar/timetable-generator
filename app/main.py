"""FastAPI entry point for the Enterprise Timetable Management System."""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from .database import engine
from . import models
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
)
from .services.settings_service import get_settings
from .database import SessionLocal

app = FastAPI(title="Timetable Generator API")

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


# ── Health & Settings bootstrap ────────────────────────────────
@app.on_event("startup")
def _bootstrap_college_settings() -> None:
    """Make sure the settings singleton row exists."""
    db = SessionLocal()
    try:
        get_settings(db)
    finally:
        db.close()


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
