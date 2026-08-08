import csv
import io
import json
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from sqlalchemy.orm import Session
from sqlalchemy import select
from app.database import get_db
from app.models.rooms import Room, RoomType
from app.models.faculty import Faculty
from app.models.groups import StudentGroup, GroupType
from app.models.subjects import Subject
from app.models.admin import Admin
from app.utils.auth import get_current_admin

router = APIRouter(prefix="/import", tags=["CSV Import"])


def parse_csv(file: UploadFile) -> list[dict]:
    content = file.file.read().decode("utf-8")
    reader = csv.DictReader(io.StringIO(content))
    return [row for row in reader]


def _atomic_import(db: Session, rows: list[dict], build) -> dict:
    """Import all-or-nothing.

    ``build(row, seen)`` must construct the ORM object and raise ``ValueError``
    with a per-row message when the row is invalid (duplicate, missing or bad
    field). Nothing is committed unless *every* row is valid, so a rejected
    upload can never leave the DB holding rows the response did not report.
    """
    pending = []
    errors = []
    for i, row in enumerate(rows, start=2):
        try:
            pending.append(build(row))
        except (KeyError, ValueError, TypeError) as e:
            errors.append({"row": i, "error": str(e)})

    if errors:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "inserted": 0,
                "errors": errors,
                "total_rows": len(rows),
                "message": "Import rejected: fix the errors and re-upload.",
            },
        )

    try:
        db.add_all(pending)
        db.commit()
    except Exception as e:  # noqa: BLE001 — integrity error at commit
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "inserted": 0,
                "errors": [{"row": None, "error": str(e)}],
                "total_rows": len(rows),
                "message": "Import rejected: fix the errors and re-upload.",
            },
        )
    return {"inserted": len(pending), "errors": [], "total_rows": len(rows)}


@router.post("/rooms")
def import_rooms(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_admin: Admin = Depends(get_current_admin)
):
    rows = parse_csv(file)
    seen = set()

    def build(row):
        room_code = (row.get("room_code") or "").strip()
        if not room_code:
            raise ValueError("room_code is required")
        if room_code in seen:
            raise ValueError(f"duplicate room_code {room_code} within the file")
        seen.add(room_code)
        existing = db.scalars(select(Room).where(
            Room.room_code == room_code)).first()
        if existing:
            raise ValueError(f"room_code {room_code} already exists")
        return Room(
            name=row["name"],
            room_code=room_code,
            room_type=RoomType(row["room_type"].upper()),
            capacity=int(row["capacity"]),
            building=row.get("building") or None,
            floor=int(row["floor"]) if row.get("floor") else None,
            has_projector=row.get("has_projector", "false").lower() == "true",
            has_ac=row.get("has_ac", "false").lower() == "true",
            equipment_json=_optional_json(row, "equipment_json"),
        )

    return _atomic_import(db, rows, build)


@router.post("/faculty")
def import_faculty(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_admin: Admin = Depends(get_current_admin)
):
    rows = parse_csv(file)
    seen = set()

    def build(row):
        email = (row.get("email") or "").strip()
        if not email:
            raise ValueError("email is required")
        if email in seen:
            raise ValueError(f"duplicate email {email} within the file")
        seen.add(email)
        existing = db.scalars(select(Faculty).where(
            Faculty.email == email)).first()
        if existing:
            raise ValueError(f"email {email} already exists")
        return Faculty(
            name=row["name"],
            email=email,
            department=row["department"],
            max_hours_per_week=int(row.get("max_hours_per_week", 20)),
            max_hours_per_day=int(row.get("max_hours_per_day", 5)),
        )

    return _atomic_import(db, rows, build)


@router.post("/groups")
def import_groups(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_admin: Admin = Depends(get_current_admin)
):
    rows = parse_csv(file)

    def build(row):
        name = (row.get("name") or "").strip()
        if not name:
            raise ValueError("name is required")
        return StudentGroup(
            name=name,
            group_type=GroupType(row["group_type"].upper()),
            department=row["department"],
            year=int(row["year"]) if row.get("year") else None,
            semester=int(row["semester"]) if row.get("semester") else None,
            strength=int(row["strength"]),
        )

    return _atomic_import(db, rows, build)


@router.post("/subjects")
def import_subjects(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_admin: Admin = Depends(get_current_admin)
):
    rows = parse_csv(file)
    seen = set()

    def build(row):
        subject_code = (row.get("subject_code") or "").strip()
        if not subject_code:
            raise ValueError("subject_code is required")
        if subject_code in seen:
            raise ValueError(f"duplicate subject_code {subject_code} within the file")
        seen.add(subject_code)
        existing = db.scalars(select(Subject).where(
            Subject.subject_code == subject_code)).first()
        if existing:
            raise ValueError(f"subject_code {subject_code} already exists")
        return Subject(
            name=row["name"],
            subject_code=subject_code,
            department=row["department"],
            semester=int(row["semester"]),
            hours_per_week=int(row["hours_per_week"]),
            requires_lab=row.get("requires_lab", "false").lower() == "true",
            requirements_json=_optional_json(row, "requirements_json"),
        )

    return _atomic_import(db, rows, build)


def _optional_json(row: dict, key: str):
    """Parse an optional CSV cell holding a JSON document.

    A blank/absent cell yields ``None``; a malformed document raises a
    ``ValueError`` (JSONDecodeError subclasses it) which the atomic importer
    turns into a per-row 422.
    """
    raw = (row.get(key) or "").strip()
    if not raw:
        return None
    return json.loads(raw)
