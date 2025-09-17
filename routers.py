from fastapi import APIRouter, HTTPException
from models import User, UserCreate, Product, ProductCreate
from typing import List

# User microservice router
user_router = APIRouter(prefix="/users", tags=["users"])

@user_router.get("/", response_model=List[User])
async def get_users():
    return [
        User(id=1, username="john_doe", email="john@example.com"),
        User(id=2, username="jane_doe", email="jane@example.com")
    ]

@user_router.post("/", response_model=User)
async def create_user(user: UserCreate):
    return User(id=3, username=user.username, email=user.email)

@user_router.get("/{user_id}", response_model=User)
async def get_user(user_id: int):
    if user_id == 1:
        return User(id=1, username="john_doe", email="john@example.com")
    raise HTTPException(status_code=404, detail="User not found")

# Product microservice router
product_router = APIRouter(prefix="/products", tags=["products"])

@product_router.get("/", response_model=List[Product])
async def get_products():
    return [
        Product(id=1, name="Laptop", description="High-end laptop", price=1299.99),
        Product(id=2, name="Mouse", description="Wireless mouse", price=29.99)
    ]

@product_router.post("/", response_model=Product)
async def create_product(product: ProductCreate):
    return Product(id=3, name=product.name, description=product.description, price=product.price)

@product_router.get("/{product_id}", response_model=Product)
async def get_product(product_id: int):
    if product_id == 1:
        return Product(id=1, name="Laptop", description="High-end laptop", price=1299.99)
    raise HTTPException(status_code=404, detail="Product not found")