from sqlalchemy import String, Boolean, Enum
from sqlalchemy.orm import Mapped, mapped_column
from database import Base
import enum

class RoomType(str, enum.Enum):
    CLASSROOM = "CLASSROOM"
    LAB = "LAB"
    SEMINAR_HALL = "SEMINAR_HALL"
    AUDITORIUM = "AUDITORIUM"

class Room(Base):
    __tablename__ = "rooms"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    room_code: Mapped[str] = mapped_column(String(20), unique=True)
    room_type: Mapped[RoomType] = mapped_column(Enum(RoomType))
    capacity: Mapped[int]
    building: Mapped[str | None] = mapped_column(String(50))
    floor: Mapped[int | None]
    has_projector: Mapped[bool] = mapped_column(Boolean, default=False)
    has_ac: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)