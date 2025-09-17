from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class User(BaseModel):
    id: Optional[int] = None
    username: str
    email: str
    created_at: Optional[datetime] = None

class UserCreate(BaseModel):
    username: str
    email: str
    password: str

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