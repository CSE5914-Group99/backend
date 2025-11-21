from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class User(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    google_uid: Optional[str] = None
    email: Optional[EmailStr] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    date_of_birth: Optional[date] = None
    preferences: Optional[str] = None


class UserCreate(BaseModel):
    email: EmailStr
    google_uid: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    date_of_birth: Optional[date] = None
    preferences: str


class UserUpdate(BaseModel):
    email: Optional[EmailStr] = None
    google_uid: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    date_of_birth: Optional[date] = None
    preferences: Optional[str] = None


class UserExists(BaseModel):
    exists: bool
    user: Optional[User] = None


class LoginRequest(BaseModel):
    email: EmailStr
    password: Optional[str] = None


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
