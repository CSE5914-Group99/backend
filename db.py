# db.py
import os, certifi
from motor.motor_asyncio import AsyncIOMotorClient
from contextlib import asynccontextmanager
from fastapi import FastAPI
from dotenv import load_dotenv

load_dotenv()

MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
DB_NAME = os.getenv("MONGODB_DB", "ClusterG99")

client = None
db = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global client, db
    client = AsyncIOMotorClient(
        MONGODB_URI,
        tls=True,
        tlsCAFile=certifi.where(),
        serverSelectionTimeoutMS=10000,
        tlsAllowInvalidCertificates=False,
    )
    db = client[DB_NAME]
    app.state.db = db   # ←—— add this line
    await db.users.create_index("username", unique=True)
    await db.users.create_index("email", unique=True)
    print("✅ Connected to MongoDB Atlas!")
    yield
    client.close()
    print("❌ MongoDB connection closed.")
