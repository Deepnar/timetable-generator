from datetime import datetime

from sqlalchemy import String, Integer, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


class AuditLog(Base):
    """One row per mutating request (POST/PUT/PATCH/DELETE).

    Written by the observability middleware so there is a durable trail of who
    changed what and when.
    """
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    method: Mapped[str] = mapped_column(String(10))
    path: Mapped[str] = mapped_column(String(300))
    status_code: Mapped[int] = mapped_column(Integer)
    admin_id: Mapped[int | None] = mapped_column(ForeignKey("admins.id"), nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
