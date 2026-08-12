from datetime import datetime

from sqlalchemy import (String, Boolean, Integer, DateTime, ForeignKey, Text)
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base
import enum


class NotificationKind(str, enum.Enum):
    """What triggered an in-app notification."""
    PUBLISH = "PUBLISH"
    CHANGE = "CHANGE"


class AppNotification(Base):
    """An in-app dashboard notification for one admin account.

    The counterpart to the publish/change emails: ``notification_service``
    fans out a row per recipient Admin (resolved by email from the Faculty /
    StudentGroup links), so every relevant person sees the same event on
    their dashboard even when SMTP is unconfigured. Emails and rows are
    dispatched together; a mail outage never affects the in-app copy.
    """
    __tablename__ = "app_notifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    recipient_admin_id: Mapped[int | None] = mapped_column(
        ForeignKey("admins.id", ondelete="CASCADE"), nullable=True)
    kind: Mapped[NotificationKind] = mapped_column(
        String(20), default=NotificationKind.PUBLISH)
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    instance_id: Mapped[int | None] = mapped_column(
        ForeignKey("timetable_instances.id", ondelete="CASCADE"), nullable=True)
    override_id: Mapped[int | None] = mapped_column(
        ForeignKey("timetable_overrides.id", ondelete="CASCADE"), nullable=True)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow)
