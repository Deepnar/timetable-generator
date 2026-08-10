from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session
from sqlalchemy import select
from app.database import get_db
from app.models.admin import Admin
from app.schemas.admin import AdminCreate, AdminResponse, AdminLogin, Token
from app.utils.auth import hash_password, verify_password, create_access_token
from app.services import redis_client

router = APIRouter(prefix="/auth", tags=["Auth"])

# Fixed-window limits per IP. Inert when Redis is disabled/unreachable.
_AUTH_LOGIN_LIMIT = 5
_AUTH_REGISTER_LIMIT = 3
_AUTH_WINDOW = 60


def _rate_limit(scope: str, limit: int, window: int):
    """Dependency: 429 when the caller's IP exceeds ``limit`` requests per
    ``window`` seconds. Returns None (allow) when Redis is unavailable."""
    def dep(request: Request) -> None:
        ip = request.client.host if request.client else "unknown"
        allowed = redis_client.check_rate_limit(scope, ip, limit, window)
        if allowed is False:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many requests, please try again later",
            )
    return dep

@router.post("/register", response_model=AdminResponse,
             status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(_rate_limit("register", _AUTH_REGISTER_LIMIT, _AUTH_WINDOW))])
def register_admin(admin: AdminCreate, db: Session = Depends(get_db)):
    existing = db.scalars(
        select(Admin).where(Admin.email == admin.email)
    ).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered"
        )
    new_admin = Admin(
        email=admin.email,
        password=hash_password(admin.password),
        name=admin.name
    )
    db.add(new_admin)
    db.commit()
    db.refresh(new_admin)
    return new_admin

@router.post("/login", response_model=Token,
             dependencies=[Depends(_rate_limit("login", _AUTH_LOGIN_LIMIT, _AUTH_WINDOW))])
def login(credentials: AdminLogin, db: Session = Depends(get_db)):
    admin = db.scalars(
        select(Admin).where(Admin.email == credentials.email)
    ).first()
    if not admin or not verify_password(credentials.password, admin.password):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid credentials"
        )
    token = create_access_token({"admin_id": admin.id})
    return {"access_token": token, "token_type": "bearer"}