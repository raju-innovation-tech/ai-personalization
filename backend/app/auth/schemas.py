import uuid

from pydantic import BaseModel, ConfigDict, EmailStr

from app.database.models.user import UserRole


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: EmailStr
    full_name: str
    role: UserRole
    is_active: bool


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ForgotPasswordResponse(BaseModel):
    message: str


class ResetPasswordRequest(BaseModel):
    email: EmailStr
    code: str
    new_password: str


class ResetPasswordResponse(BaseModel):
    message: str
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserOut
