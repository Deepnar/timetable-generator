"""Schemas for the teacher/student self-service portal (/my/*, DD-022 #1)."""
from pydantic import BaseModel
from typing import Optional
from datetime import date, time


class MyFaculty(BaseModel):
    id: int
    name: str
    email: str
    department: str


class MyGroup(BaseModel):
    id: int
    name: str
    department: str
    year: int | None = None
    semester: int | None = None


class MySlot(BaseModel):
    id: int
    day_of_week: int | None
    slot_number: int
    start_time: time
    end_time: time
    subject_code: str | None = None
    subject_name: str | None = None
    room_code: str | None = None
    group_name: str | None = None
    faculty_name: str | None = None
    session_type: str
    is_manual_override: bool = False


class MyScheduleResponse(BaseModel):
    """The caller's own published schedule (teacher portal).

    ``faculty`` is None when the teacher account's email matches no Faculty
    row (provisioned login without a teaching record); the UI then shows an
    empty state rather than a schedule.
    """
    faculty: MyFaculty | None
    slots: list[MySlot]
    published_instance_ids: list[int]


class MyTimetableResponse(BaseModel):
    """The caller's group published timetable (student portal).

    ``group`` is None when the student account's email matches no
    ``StudentGroup.student_email``; the UI then shows an empty state.
    """
    group: MyGroup | None
    slots: list[MySlot]
    published_instance_ids: list[int]


class MyTodayResponse(BaseModel):
    """The caller's sessions for the current weekday (day-card data)."""
    faculty: MyFaculty | None = None
    group: MyGroup | None = None
    day_of_week: int
    slots: list[MySlot]
