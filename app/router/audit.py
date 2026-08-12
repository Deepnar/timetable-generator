"""Read access to the audit trail (mutations recorded by the middleware)."""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Response
from sqlalchemy import select
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.database import get_db
from app.utils.auth import require_roles
from app.models.audit import AuditLog
from app.utils.pagination import Pagination, pagination, paginate

router = APIRouter(prefix="/audit", tags=["Audit"],
                 dependencies=[Depends(require_roles("admin"))])


class AuditLogResponse(BaseModel):
    id: int
    method: str
    path: str
    status_code: int
    admin_id: Optional[int] = None
    request_id: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


@router.get("/", response_model=list[AuditLogResponse])
def list_audit(
    response: Response,
    method: Optional[str] = None,
    admin_id: Optional[int] = None,
    status_code: Optional[int] = None,
    page: Pagination = Depends(pagination),
    db: Session = Depends(get_db),
):
    """Most-recent-first audit entries, filterable and paginated."""
    query = select(AuditLog).order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
    if method:
        query = query.where(AuditLog.method == method.upper())
    if admin_id is not None:
        query = query.where(AuditLog.admin_id == admin_id)
    if status_code is not None:
        query = query.where(AuditLog.status_code == status_code)
    return paginate(db, query, page, response)
