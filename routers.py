from fastapi import APIRouter, HTTPException, Request, Depends
from models import User, UserCreate, UserUpdate, Product, ProductCreate
from typing import List
from datetime import datetime
from passlib.hash import bcrypt
from bson import ObjectId
from db import db   # from db.py

user_router = APIRouter(prefix="/users", tags=["users"])

def get_db(request: Request):
    db = getattr(request.app.state, "db", None)
    if db is None:
        # This would be rare, but helps during dev if startup failed.
        raise HTTPException(status_code=503, detail="Database not initialized")
    return db

def _to_user(doc) -> User:
    return User(
        id=None,
        username=doc["username"],
        email=doc["email"],
        created_at=doc.get("created_at")
    )

@user_router.get("/", response_model=List[User])
async def get_users(db=Depends(get_db)):
    docs = await db.users.find({}, {"password": 0}).sort("_id", -1).to_list(1000)
    return [_to_user(d) for d in docs]

@user_router.post("/", response_model=User)
async def create_user(user: UserCreate, db=Depends(get_db)):
    exists = await db.users.find_one({"$or": [{"username": user.username}, {"email": user.email}]})
    if exists:
        raise HTTPException(status_code=400, detail="Username or email already exists")
    created_at = datetime.utcnow().isoformat()
    await db.users.insert_one({
        "username": user.username,
        "email": user.email,
        "password": bcrypt.hash(user.password),
        "created_at": created_at
    })
    return User(username=user.username, email=user.email, created_at=created_at)

@user_router.get("/{user_id}", response_model=User)
async def get_user(user_id: str, db=Depends(get_db)):
    query = {"_id": ObjectId(user_id)} if ObjectId.is_valid(user_id) else {"username": user_id}
    doc = await db.users.find_one(query, {"password": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="User not found")
    return _to_user(doc)

@user_router.patch("/{user_id}", response_model=User)
async def update_user(user_id: str, user: UserUpdate, db=Depends(get_db)):
    query = {"_id": ObjectId(user_id)} if ObjectId.is_valid(user_id) else {"username": user_id}
    update_doc = {}
    if user.username is not None: update_doc["username"] = user.username
    if user.email    is not None: update_doc["email"] = user.email
    if user.password is not None: update_doc["password"] = bcrypt.hash(user.password)

    if not update_doc:
        doc = await db.users.find_one(query, {"password": 0})
        if not doc: raise HTTPException(status_code=404, detail="User not found")
        return _to_user(doc)

    if "username" in update_doc or "email" in update_doc:
        conds = []
        if "username" in update_doc: conds.append({"username": update_doc["username"]})
        if "email"    in update_doc: conds.append({"email": update_doc["email"]})
        exists = await db.users.find_one(
            {"$or": conds, **({"_id": {"$ne": query.get("_id")}} if "_id" in query else {})}
        )
        if exists:
            raise HTTPException(status_code=400, detail="Username or email already exists")

    result = await db.users.find_one_and_update(
        query, {"$set": update_doc}, return_document=True, projection={"password": 0}
    )
    if not result:
        raise HTTPException(status_code=404, detail="User not found")
    return _to_user(result)

@user_router.delete("/{user_id}")
async def delete_user(user_id: str, db=Depends(get_db)):
    query = {"_id": ObjectId(user_id)} if ObjectId.is_valid(user_id) else {"username": user_id}
    res = await db.users.delete_one(query)
    if not res.deleted_count:
        raise HTTPException(status_code=404, detail="User not found")
    return {"message": "User deleted successfully"}


#-------------------------------------------------------------------------------------S

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