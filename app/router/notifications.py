"""In-app notification endpoints (DD-027).

Dashboard bell: list the caller's notifications (newest first), count unread,
and mark individual or all rows read. Rows are created by
``notification_service`` on publish and mid-year change.
"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.admin import Admin
from app.models.notifications import AppNotification, NotificationKind
from app.utils.auth import get_current_admin, require_roles
from app.utils.pagination import Pagination, pagination, paginate
from pydantic import BaseModel
from typing import Optional


class NotificationResponse(BaseModel):
    id: int
    kind: NotificationKind
    title: str
    body: Optional[str]
    instance_id: Optional[int]
    override_id: Optional[int]
    is_read: bool
    created_at: datetime

    class Config:
        from_attributes = True


class UnreadCount(BaseModel):
    unread: int


class ReadAllResponse(BaseModel):
    marked: int


router = APIRouter(
    prefix="/notifications", tags=["Notifications"],
    # Notifications are recipient-scoped: every route filters by the caller's
    # admin id (``recipient_admin_id == current.id``), and all four roles
    # legitimately receive them (a teacher's cover, a student's class change).
    # The guard makes the authentication requirement explicit rather than
    # restricting the bell to admins, which would break the portal.
    dependencies=[Depends(require_roles("admin", "hod", "teacher", "student"))])


@router.get("/", response_model=list[NotificationResponse])
def list_notifications(
    response: Response,
    unread_only: bool = False,
    page: Pagination = Depends(pagination),
    db: Session = Depends(get_db),
    current: Admin = Depends(get_current_admin),
):
    """The caller's notifications, newest first, with X-Total-Count."""
    query = select(AppNotification).where(
        AppNotification.recipient_admin_id == current.id)
    if unread_only:
        query = query.where(AppNotification.is_read == False)  # noqa: E712
    query = query.order_by(AppNotification.created_at.desc())
    return paginate(db, query, page, response)


@router.get("/unread-count", response_model=UnreadCount)
def unread_count(db: Session = Depends(get_db),
                 current: Admin = Depends(get_current_admin)):
    """How many unread notifications the caller has (the bell badge)."""
    total = db.scalar(
        select(func.count()).select_from(AppNotification).where(
            AppNotification.recipient_admin_id == current.id,
            AppNotification.is_read == False,  # noqa: E712
        )
    )
    return UnreadCount(unread=total or 0)


@router.post("/{notification_id}/read", response_model=NotificationResponse)
def mark_read(notification_id: int, db: Session = Depends(get_db),
              current: Admin = Depends(get_current_admin)):
    notification = db.scalars(
        select(AppNotification).where(
            AppNotification.id == notification_id,
            AppNotification.recipient_admin_id == current.id,
        )
    ).first()
    if not notification:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Notification not found")
    notification.is_read = True
    db.commit()
    db.refresh(notification)
    return notification


@router.post("/read-all", response_model=ReadAllResponse)
def mark_all_read(db: Session = Depends(get_db),
                  current: Admin = Depends(get_current_admin)):
    unread = db.scalars(
        select(AppNotification).where(
            AppNotification.recipient_admin_id == current.id,
            AppNotification.is_read == False,  # noqa: E712
        )
    ).all()
    for n in unread:
        n.is_read = True
    db.commit()
    return ReadAllResponse(marked=len(unread))
