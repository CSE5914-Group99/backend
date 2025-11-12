from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr


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


class UserCreate(BaseModel):
    username: str
    email: EmailStr
    password: str
    google_uid: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    date_of_birth: Optional[date] = None


class UserUpdate(BaseModel):
    username: Optional[str] = None
    email: Optional[EmailStr] = None
    password: Optional[str] = None
    google_uid: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    date_of_birth: Optional[date] = None


class LoginRequest(BaseModel):
    username_or_email: str
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
