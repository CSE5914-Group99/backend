from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime

class User(BaseModel):
    id: Optional[int] = None
    username: str
    email: EmailStr
    created_at: Optional[datetime] = None

class UserCreate(BaseModel):
    username: str
    email: EmailStr
    password: str

# NEW: partial update (all optional)
class UserUpdate(BaseModel):
    username: Optional[str] = None
    email: Optional[EmailStr] = None
    password: Optional[str] = None

# NEW: login & token
class LoginRequest(BaseModel):
    username_or_email: str
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"

class Product(BaseModel):
    id: Optional[int] = None
    name: str
    description: str
    price: float
    in_stock: bool = True
    created_at: Optional[datetime] = None

class ProductCreate(BaseModel):
    name: str
    description: str
    price: float