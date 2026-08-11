from datetime import datetime, timedelta
import bcrypt
from jose import JWTError, jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer
from sqlalchemy.orm import Session
from sqlalchemy import select
from ..config import settings
from ..database import get_db
from ..models import Admin
from ..schemas import TokenData

security = HTTPBearer()

# bcrypt operates on the first 72 bytes of a password. Older passlib used to
# truncate silently; bcrypt>=4.1 raises instead, so we truncate explicitly.
_BCRYPT_MAX_BYTES = 72


def hash_password(password: str) -> str:
    pwd = password.encode("utf-8")[:_BCRYPT_MAX_BYTES]
    return bcrypt.hashpw(pwd, bcrypt.gensalt()).decode("utf-8")

def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(
            plain.encode("utf-8")[:_BCRYPT_MAX_BYTES],
            hashed.encode("utf-8"),
        )
    except (ValueError, TypeError):
        return False

def create_access_token(data: dict, role: str = "admin") -> str:
    to_encode = data.copy()
    to_encode.update({"role": role})
    expire = datetime.utcnow() + timedelta(
        minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )
    to_encode.update({"exp": expire})
    return jwt.encode(
        to_encode,
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM
    )

def authenticate_token(token: str, db: Session) -> Admin | None:
    """Validate a bearer token and return the active admin, or ``None``.

    Shared by the ``get_current_admin`` dependency and the global auth
    middleware in ``app.main`` so every non-exempt request is checked the
    same way.
    """
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM]
        )
        admin_id: int | None = payload.get("admin_id")
        if admin_id is None:
            return None
    except JWTError:
        return None

    admin = db.scalars(
        select(Admin).where(Admin.id == admin_id)
    ).first()

    if not admin or not admin.is_active:
        return None

    return admin


def get_current_admin(
    credentials=Depends(security),
    db: Session = Depends(get_db)
) -> Admin:
    admin = authenticate_token(credentials.credentials, db)
    if admin is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return admin


def token_role(token: str) -> str | None:
    """The role claim from a bearer token (best-effort, no DB hit)."""
    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
        )
        return payload.get("role")
    except JWTError:
        return None


def require_roles(*allowed: str):
    """Dependency factory: 403 unless the token's role is in ``allowed``.

    Used on endpoints that are finer-grained than the global auth gate (which
    only checks "is there a valid token"). The role rides in the JWT so this
    needs no DB lookup.
    """
    def dep(credentials=Depends(security)) -> None:
        role = token_role(credentials.credentials)
        if role is None or role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions for this role",
            )
    return dep