from pydantic import BaseModel, EmailStr, Field
from app.models.admin import AdminRole

class AdminCreate(BaseModel):
    name: str
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    role: AdminRole = AdminRole.ADMIN


class RegisterRequest(BaseModel):
    """Public self-registration — deliberately has NO role field.

    Self-registration must never grant elevated roles (a public endpoint
    accepting a role would be vertical privilege escalation). The account is
    created with the least-privilege default; admins provision other roles via
    ``POST /auth/users``.
    """
    name: str
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)

class AdminResponse(BaseModel):
    id: int
    name: str
    email: EmailStr
    is_active: bool
    role: AdminRole

    class Config:
        from_attributes = True

class AdminLogin(BaseModel):
    email: EmailStr
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    id: int | None = None

class MeResponse(BaseModel):
    id: int
    name: str
    email: EmailStr
    role: AdminRole