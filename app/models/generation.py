from sqlalchemy import String, Boolean, Enum, Text, DateTime, ForeignKey, Integer, Date, Time
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base
from datetime import datetime, date, time
import enum

class GenerationStatus(str, enum.Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"

class TimetableType(str, enum.Enum):
    CLASS = "CLASS"
    FACULTY = "FACULTY"
    ROOM = "ROOM"
    EVENT = "EVENT"
    EXAM = "EXAM"
    IP = "IP"
    CUSTOM = "CUSTOM"

class InstanceStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    SELECTED = "SELECTED"
    PUBLISHED = "PUBLISHED"
    ARCHIVED = "ARCHIVED"

class SessionType(str, enum.Enum):
    LECTURE = "LECTURE"
    LAB = "LAB"
    TUTORIAL = "TUTORIAL"
    SEMINAR = "SEMINAR"
    EVENT = "EVENT"
    EXAM = "EXAM"
    IP = "IP"
    FREE = "FREE"

class AlgorithmType(str, enum.Enum):
    GREEDY = "GREEDY"
    OR_TOOLS = "OR_TOOLS"

class TimetableGeneration(Base):
    __tablename__ = "timetable_generations"

    id: Mapped[int] = mapped_column(primary_key=True)
    profile_id: Mapped[int | None] = mapped_column(
        ForeignKey("timetable_profiles.id"))
    combination_id: Mapped[int | None] = mapped_column(
        ForeignKey("profile_combinations.id"))
    academic_year: Mapped[str] = mapped_column(String(10))
    semester: Mapped[int | None]
    timetable_type: Mapped[TimetableType] = mapped_column(Enum(TimetableType))
    generation_status: Mapped[GenerationStatus] = mapped_column(
        Enum(GenerationStatus), default=GenerationStatus.PENDING)
    algorithm_used: Mapped[AlgorithmType] = mapped_column(
        Enum(AlgorithmType), default=AlgorithmType.GREEDY)
    instances_requested: Mapped[int] = mapped_column(default=3)
    instances_produced: Mapped[int] = mapped_column(default=0)
    score_best_instance: Mapped[float | None]
    run_duration_ms: Mapped[int | None]
    triggered_by: Mapped[int] = mapped_column(ForeignKey("admins.id"))
    triggered_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)
    error_log: Mapped[str | None] = mapped_column(Text)

class TimetableInstance(Base):
    __tablename__ = "timetable_instances"

    id: Mapped[int] = mapped_column(primary_key=True)
    generation_id: Mapped[int] = mapped_column(
        ForeignKey("timetable_generations.id"))
    instance_number: Mapped[int]
    label: Mapped[str | None] = mapped_column(String(100))
    soft_score: Mapped[float | None]
    hard_violations: Mapped[int] = mapped_column(default=0)
    status: Mapped[InstanceStatus] = mapped_column(
        Enum(InstanceStatus), default=InstanceStatus.DRAFT)
    selected_by: Mapped[int | None] = mapped_column(ForeignKey("admins.id"))
    selected_at: Mapped[datetime | None] = mapped_column(DateTime)
    published_at: Mapped[datetime | None] = mapped_column(DateTime)
    notes: Mapped[str | None] = mapped_column(Text)

class TimetableSlot(Base):
    __tablename__ = "timetable_slots"

    id: Mapped[int] = mapped_column(primary_key=True)
    instance_id: Mapped[int] = mapped_column(
        ForeignKey("timetable_instances.id", ondelete="CASCADE"))
    slot_date: Mapped[date | None] = mapped_column(Date)
    day_of_week: Mapped[int | None]
    slot_number: Mapped[int]
    start_time: Mapped[time] = mapped_column(Time)
    end_time: Mapped[time] = mapped_column(Time)
    subject_id: Mapped[int | None] = mapped_column(ForeignKey("subjects.id"))
    faculty_id: Mapped[int | None] = mapped_column(ForeignKey("faculty.id"))
    room_id: Mapped[int | None] = mapped_column(ForeignKey("rooms.id"))
    student_group_id: Mapped[int | None] = mapped_column(
        ForeignKey("student_groups.id"))
    session_type: Mapped[SessionType] = mapped_column(Enum(SessionType))
    is_manual_override: Mapped[bool] = mapped_column(Boolean, default=False)
    override_reason: Mapped[str | None] = mapped_column(String(300))
    external_speaker: Mapped[str | None] = mapped_column(String(200))
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow)
