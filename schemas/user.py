from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class User(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: Optional[int] = None
    username: str
    google_uid: Optional[str] = None
    email: EmailStr
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    date_of_birth: Optional[date] = None
    created_at: Optional[datetime] = None
    preferences: dict[str, Any] = Field(default_factory=dict)


class UserCreate(BaseModel):
    username: str
    email: EmailStr
    google_uid: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    date_of_birth: Optional[date] = None
    preferences: dict[str, Any] = Field(default_factory=dict)


class UserUpdate(BaseModel):
    username: Optional[str] = None
    email: Optional[EmailStr] = None
    google_uid: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    date_of_birth: Optional[date] = None
    preferences: Optional[dict[str, Any]] = None


class UserExists(BaseModel):
    exists: bool
    user: Optional[User] = None


class LoginRequest(BaseModel):
    username_or_email: str
    password: Optional[str] = None


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
