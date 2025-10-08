from fastapi import APIRouter, HTTPException
from models import User, UserCreate, Product, ProductCreate
from typing import List
from datetime import datetime
import sqlite3

# Simple SQLite setup for user — file is in project root
DB_PATH = "users.db"

def _conn():
    return sqlite3.connect(DB_PATH, check_same_thread=False)

def _init_users_table():
    conn = _conn()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            email TEXT NOT NULL UNIQUE,
            password TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()

_init_users_table()

# User microservice router
user_router = APIRouter(prefix="/users", tags=["users"])

@user_router.get("/", response_model=List[User])
async def get_users():
    conn = _conn()
    cur = conn.cursor()
    cur.execute("SELECT id, username, email, created_at FROM users ORDER BY id DESC")
    rows = cur.fetchall()
    conn.close()
    return [
        User(id=row[0], username=row[1], email=row[2], created_at=row[3])
        for row in rows
    ]

@user_router.post("/", response_model=User)
async def create_user(user: UserCreate):
    conn = _conn()
    cur = conn.cursor()

    # Uniqueness checks
    cur.execute("SELECT id FROM users WHERE username=? OR email=?", (user.username, user.email))
    exists = cur.fetchone()
    if exists:
        conn.close()
        raise HTTPException(status_code=400, detail="Username or email already exists")

    created_at = datetime.utcnow().isoformat()
    try:
        cur.execute(
            "INSERT INTO users (username, email, password, created_at) VALUES (?, ?, ?, ?)",
            (user.username, user.email, user.password, created_at)
        )
        conn.commit()
        user_id = cur.lastrowid
    finally:
        conn.close()

    return User(id=user_id, username=user.username, email=user.email, created_at=created_at)

@user_router.get("/{user_id}", response_model=User)
async def get_user(user_id: int):
    conn = _conn()
    cur = conn.cursor()
    cur.execute("SELECT id, username, email, created_at FROM users WHERE id=?", (user_id,))
    row = cur.fetchone()
    conn.close()

    if not row:
        raise HTTPException(status_code=404, detail="User not found")

    return User(id=row[0], username=row[1], email=row[2], created_at=row[3])

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