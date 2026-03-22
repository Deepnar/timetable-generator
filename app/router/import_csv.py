import csv
import io
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


@router.post("/rooms")
def import_rooms(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_admin: Admin = Depends(get_current_admin)
):
    rows = parse_csv(file)
    inserted = 0
    errors = []

    for i, row in enumerate(rows, start=2):
        try:
            # check for duplicate room_code
            if row.get("room_code"):
                existing = db.scalars(select(Room).where(
                    Room.room_code == row["room_code"]
                )).first()
                if existing:
                    errors.append({
                        "row": i,
                        "error": f"room_code {row['room_code']} already exists"
                    })
                    continue

            room = Room(
                name=row["name"],
                room_code=row.get("room_code") or None,
                room_type=RoomType(row["room_type"].upper()),
                capacity=int(row["capacity"]),
                building=row.get("building") or None,
                floor=int(row["floor"]) if row.get("floor") else None,
                has_projector=row.get("has_projector", "false").lower() == "true",
                has_ac=row.get("has_ac", "false").lower() == "true",
            )
            db.add(room)
            inserted += 1
        except Exception as e:
            errors.append({"row": i, "error": str(e)})

    db.commit()
    return {
        "inserted": inserted,
        "errors": errors,
        "total_rows": len(rows)
    }


@router.post("/faculty")
def import_faculty(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_admin: Admin = Depends(get_current_admin)
):
    rows = parse_csv(file)
    inserted = 0
    errors = []

    for i, row in enumerate(rows, start=2):
        try:
            existing = db.scalars(select(Faculty).where(
                Faculty.email == row["email"]
            )).first()
            if existing:
                errors.append({
                    "row": i,
                    "error": f"email {row['email']} already exists"
                })
                continue

            faculty = Faculty(
                name=row["name"],
                email=row["email"],
                department=row["department"],
                max_hours_per_week=int(row.get("max_hours_per_week", 20)),
                max_hours_per_day=int(row.get("max_hours_per_day", 5)),
            )
            db.add(faculty)
            inserted += 1
        except Exception as e:
            errors.append({"row": i, "error": str(e)})

    db.commit()
    return {
        "inserted": inserted,
        "errors": errors,
        "total_rows": len(rows)
    }


@router.post("/groups")
def import_groups(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_admin: Admin = Depends(get_current_admin)
):
    rows = parse_csv(file)
    inserted = 0
    errors = []

    for i, row in enumerate(rows, start=2):
        try:
            group = StudentGroup(
                name=row["name"],
                group_type=GroupType(row["group_type"].upper()),
                department=row["department"],
                year=int(row["year"]) if row.get("year") else None,
                semester=int(row["semester"]) if row.get("semester") else None,
                strength=int(row["strength"]),
            )
            db.add(group)
            inserted += 1
        except Exception as e:
            errors.append({"row": i, "error": str(e)})

    db.commit()
    return {
        "inserted": inserted,
        "errors": errors,
        "total_rows": len(rows)
    }


@router.post("/subjects")
def import_subjects(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_admin: Admin = Depends(get_current_admin)
):
    rows = parse_csv(file)
    inserted = 0
    errors = []

    for i, row in enumerate(rows, start=2):
        try:
            existing = db.scalars(select(Subject).where(
                Subject.subject_code == row["subject_code"]
            )).first()
            if existing:
                errors.append({
                    "row": i,
                    "error": f"subject_code {row['subject_code']} already exists"
                })
                continue

            subject = Subject(
                name=row["name"],
                subject_code=row["subject_code"],
                department=row["department"],
                semester=int(row["semester"]),
                hours_per_week=int(row["hours_per_week"]),
                requires_lab=row.get("requires_lab", "false").lower() == "true",
            )
            db.add(subject)
            inserted += 1
        except Exception as e:
            errors.append({"row": i, "error": str(e)})

    db.commit()
    return {
        "inserted": inserted,
        "errors": errors,
        "total_rows": len(rows)
    }