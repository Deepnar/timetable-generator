"""Reusable offset/limit pagination for list endpoints.

Usage in a router::

    @router.get("/")
    def list_things(response: Response, page: Pagination = Depends(pagination),
                    db: Session = Depends(get_db)):
        query = select(Thing).where(...)
        return paginate(db, query, page, response)

``paginate`` applies ``offset``/``limit`` and sets an ``X-Total-Count`` header
with the unpaginated total so clients can render pagination controls.
"""
from dataclasses import dataclass

from fastapi import Query, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session


@dataclass
class Pagination:
    skip: int
    limit: int


def pagination(
    skip: int = Query(0, ge=0, description="Number of rows to skip"),
    limit: int = Query(50, ge=1, le=200, description="Maximum rows to return"),
) -> Pagination:
    return Pagination(skip=skip, limit=limit)


def paginate(db: Session, query, page: Pagination, response: Response):
    """Return one page of ``query`` and set the ``X-Total-Count`` header."""
    total = db.scalar(select(func.count()).select_from(query.order_by(None).subquery()))
    response.headers["X-Total-Count"] = str(total or 0)
    return db.scalars(query.offset(page.skip).limit(page.limit)).all()
