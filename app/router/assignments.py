"""Routes for the Subject-Faculty-Group mapping triad.

This is the single source of truth for *who teaches what to which division*
and the table the greedy solver expands into individual sessions.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Admin
from app.models.subject_assignments import SubjectAssignment
from app.models.subjects import Subject
from app.models.faculty import Faculty
from app.models.groups import StudentGroup
from app.utils.pagination import Pagination, pagination, paginate
from app.schemas.assignments import (
    SubjectAssignmentCreate,
    SubjectAssignmentResponse,
    SubjectAssignmentUpdate,
)
from app.utils.auth import get_current_admin, require_roles

router = APIRouter(prefix="/assignments", tags=["Subject Assignments"],
                 dependencies=[Depends(require_roles("admin", "hod"))])


def _validate_dependencies(payload, db: Session) -> None:
    """Make sure subject / faculty / group all exist before inserting."""
    if not db.get(Subject, payload.subject_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Subject {payload.subject_id} not found",
        )
    if payload.faculty_id is not None and not db.get(Faculty, payload.faculty_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Faculty {payload.faculty_id} not found",
        )
    if not db.get(StudentGroup, payload.group_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Student group {payload.group_id} not found",
        )


@router.get("/", response_model=list[SubjectAssignmentResponse])
def list_assignments(
    response: Response,
    subject_id: Optional[int] = None,
    faculty_id: Optional[int] = None,
    group_id: Optional[int] = None,
    page: Pagination = Depends(pagination),
    db: Session = Depends(get_db),
):
    query = select(SubjectAssignment)
    if subject_id is not None:
        query = query.where(SubjectAssignment.subject_id == subject_id)
    if faculty_id is not None:
        query = query.where(SubjectAssignment.faculty_id == faculty_id)
    if group_id is not None:
        query = query.where(SubjectAssignment.group_id == group_id)
    return paginate(db, query, page, response)


@router.get("/{assignment_id}", response_model=SubjectAssignmentResponse)
def get_assignment(
    assignment_id: int,
    db: Session = Depends(get_db),
):
    assignment = db.get(SubjectAssignment, assignment_id)
    if not assignment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Assignment {assignment_id} not found",
        )
    return assignment


@router.post(
    "/",
    response_model=SubjectAssignmentResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_assignment(
    payload: SubjectAssignmentCreate,
    db: Session = Depends(get_db),
    _: Admin = Depends(get_current_admin),
):
    _validate_dependencies(payload, db)
    assignment = SubjectAssignment(**payload.model_dump())
    db.add(assignment)
    db.commit()
    db.refresh(assignment)
    return assignment


@router.put("/{assignment_id}", response_model=SubjectAssignmentResponse)
def update_assignment(
    assignment_id: int,
    payload: SubjectAssignmentUpdate,
    db: Session = Depends(get_db),
    _: Admin = Depends(get_current_admin),
):
    assignment = db.get(SubjectAssignment, assignment_id)
    if not assignment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Assignment {assignment_id} not found",
        )
    if payload.faculty_id is not None and not db.get(Faculty, payload.faculty_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Faculty {payload.faculty_id} not found",
        )
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(assignment, key, value)
    db.commit()
    db.refresh(assignment)
    return assignment


@router.delete("/{assignment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_assignment(
    assignment_id: int,
    db: Session = Depends(get_db),
    _: Admin = Depends(get_current_admin),
):
    assignment = db.get(SubjectAssignment, assignment_id)
    if not assignment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Assignment {assignment_id} not found",
        )
    db.delete(assignment)
    db.commit()
    return
