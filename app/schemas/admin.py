from pydantic import BaseModel, EmailStr
from app.models.admin import AdminRole

class AdminCreate(BaseModel):
    name: str
    email: EmailStr
    password: str
    role: AdminRole = AdminRole.ADMIN

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