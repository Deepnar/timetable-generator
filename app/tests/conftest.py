"""In-process test client with an in-memory SQLite database.

We can't talk to Postgres in CI/sandbox, and we don't have pytest
available either, so this conftest exposes a hand-rolled test runner
that:

* overrides the engine used by ``app.database`` and the
  ``CollegeSettings`` singleton service,
* creates all tables on the in-memory SQLite DB,
* hands back a FastAPI ``TestClient`` plus a session factory.

Because every router pulls in ``from app.database import get_db``,
we monkey-patch the attribute on the *module* itself (which is exactly
what the routers imported), not on the dotted path.
"""
from __future__ import annotations

import os
import sys
from typing import Iterator

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..", "..")))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

TEST_DB_URL = "sqlite:///:memory:"
engine = create_engine(
    TEST_DB_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(
    autocommit=False, autoflush=False, bind=engine
)

# Bring the app modules online BEFORE we patch the DB bits.
import app.database as app_db  # noqa: E402
app_db.engine = engine
app_db.SessionLocal = TestingSessionLocal

# The suite has no Redis: force the redis client to a no-op so caching, rate
# limiting, and generation locking are inert in every test unless a test
# explicitly substitutes a fake client (see test_redis_integration.py).
from app.config import settings as _app_settings  # noqa: E402
_app_settings.REDIS_ENABLED = False

# The suite has no SMTP server: force the mailer off so publish never attempts
# a network send. Tests that exercise the mailer enable it and substitute a
# fake delivery layer (see test_email_notifications.py).
_app_settings.EMAIL_ENABLED = False


def _get_db_override() -> Iterator:
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


# This is the *module attribute*; every router does
# `from app.database import get_db`, so each of them already holds a
# reference to this exact function object. Patching the module attribute
# below changes the binding inside `app.database`, and re-importing from
# it would yield the override.  We also reach into the routers and patch
# their local `get_db` names so the override takes effect immediately.
app_db.get_db = _get_db_override

import importlib  # noqa: E402

for module_name in (
    "app.router.auth",
    "app.router.export",
    "app.router.generate",
    "app.router.history",
    "app.router.import_csv",
    "app.router.instances",
    "app.router.reset",
    "app.router.settings",
    "app.router.assignments",
    "app.router.audit",
    "app.router.rooms",
    "app.router.faculty",
    "app.router.groups",
    "app.router.subjects",
    "app.router.profiles",
    "app.router.constraints",
    "app.router.room_blackout",
    "app.router.faculty_availibility",
):
    try:
        mod = importlib.import_module(module_name)
    except ModuleNotFoundError:
        continue
    if hasattr(mod, "get_db"):
        mod.get_db = _get_db_override

# Make sure all models are registered on the Base metadata.
from app import models  # noqa: F401, E402
from app.database import Base  # noqa: E402

Base.metadata.create_all(bind=engine)


def reset_db() -> None:
    """Wipe all data between tests but keep the schema."""
    for table in reversed(Base.metadata.sorted_tables):
        with engine.begin() as conn:
            conn.execute(table.delete())


# ── Test client + helpers ────────────────────────────────────
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.utils.auth import hash_password  # noqa: E402
from app.models.admin import Admin  # noqa: E402
from app.services.settings_service import get_settings  # noqa: E402


def make_client() -> TestClient:
    return TestClient(app)


def create_admin(
    email: str = "admin@example.com",
    password: str = "admin123",
    name: str = "Test Admin",
) -> Admin:
    db = TestingSessionLocal()
    try:
        admin = Admin(
            email=email,
            name=name,
            password=hash_password(password),
            is_active=True,
        )
        db.add(admin)
        db.commit()
        db.refresh(admin)
        return admin
    finally:
        db.close()


def login_token(client: TestClient, email="admin@example.com", password="admin123") -> str:
    r = client.post("/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def ensure_settings(defaults=None) -> None:
    db = TestingSessionLocal()
    try:
        s = get_settings(db)
        if defaults:
            for k, v in defaults.items():
                setattr(s, k, v)
            db.commit()
    finally:
        db.close()
