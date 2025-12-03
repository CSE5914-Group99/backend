
import asyncio
from sqlalchemy import text
from db.session import get_session

async def inspect_db():
    async for session in get_session():
        print("Connected to DB")
        try:
            # Inspect users
            result = await session.execute(text("SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'users';"))
            columns = result.fetchall()
            print("Columns in 'users' table:")
            for col in columns:
                print(f"- {col[0]} ({col[1]})")
            
            # Inspect schedules
            result = await session.execute(text("SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'schedules';"))
            columns = result.fetchall()
            print("\nColumns in 'schedules' table:")
            for col in columns:
                print(f"- {col[0]} ({col[1]})")

        except Exception as e:
            print(f"Error: {e}")
        return

if __name__ == "__main__":
    asyncio.run(inspect_db())
