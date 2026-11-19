from __future__ import annotations

from datetime import datetime
import uuid

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.enums import UserRole


class UserBase(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=1, max_length=200)


class UserCreate(UserBase):
    password: str = Field(min_length=8, max_length=128)


class UserUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=200)
    email: EmailStr | None = None


class UserResponse(UserBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    role: UserRole
    is_active: bool
    is_verified: bool
    created_at: datetime
    updated_at: datetime


class AdminRoleUpdate(BaseModel):
    role: UserRole


class AdminStatusUpdate(BaseModel):
    is_active: bool | None = None
    is_verified: bool | None = None
