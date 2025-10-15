import os, asyncio, certifi
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv()
uri = os.getenv("MONGODB_URI")
print("🔍 URI =", uri)

async def main():
    try:
        client = AsyncIOMotorClient(
            uri,
            tls=True,
            tlsCAFile=certifi.where(),
            serverSelectionTimeoutMS=10000,
            tlsAllowInvalidCertificates=False,
        )
        await client.server_info()  # force handshake
        print("✅ Connected successfully!")
        print("Databases:", await client.list_database_names())
    except Exception as e:
        print("❌ Connection failed:", e)

asyncio.run(main())
