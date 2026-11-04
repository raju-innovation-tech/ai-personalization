from pydantic import BaseModel, EmailStr, Field, model_validator

from app.database.models.user import UserRole


class UserCreateIn(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)
    full_name: str | None = Field(default=None, max_length=255)
    role: UserRole = UserRole.VIEWER


class UserUpdateIn(BaseModel):
    email: EmailStr | None = None
    full_name: str | None = Field(default=None, min_length=1, max_length=255)
    role: UserRole | None = None
    is_active: bool | None = None
    password: str | None = Field(default=None, min_length=8, max_length=128)

    @model_validator(mode="after")
    def at_least_one_field(self) -> "UserUpdateIn":
        if all(v is None for v in (self.email, self.full_name, self.role, self.is_active, self.password)):
            raise ValueError("send at least one field to change")
        return self
