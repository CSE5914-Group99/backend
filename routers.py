# routers.py
from fastapi import APIRouter, status
from typing import List, Optional, Dict, Any
# Use your existing user models
from models import User, UserCreate, UserUpdate, ScheduleLoadRequest, ScheduleLoadResult, ScheduleSaved, ScheduleItem, SchedulePayload
from pydantic import BaseModel, Field

# ---------------------------------------------------------
# Routers
# ---------------------------------------------------------
schedule_router = APIRouter(prefix="/schedule", tags=["schedule"])
users_router    = APIRouter(prefix="/users",    tags=["users"])

# =======================
# SCHEDULE
# =======================

@schedule_router.get(
    "/{userId}",
    response_model=List[ScheduleSaved],
    summary="Gets all of the user's saved schedules",
)
async def get_user_schedules(userId: str):
    # TODO: query Postgres
    return [
        ScheduleSaved(
            scheduleId="sch_1",
            userId=userId,
            name="Spring Plan",
            items=[ScheduleItem(courseId="CSE-2221", sectionId="001")],
            favorite=False,
        )
    ]

@schedule_router.get(
    "/favorite/{userId}",
    response_model=Optional[ScheduleSaved],
    summary="Gets the user's favorite schedule",
)
async def get_favorite_schedule(userId: str):
    # TODO: query favorite in Postgres
    return ScheduleSaved(
        scheduleId="sch_fav",
        userId=userId,
        name="Favorite Plan",
        items=[ScheduleItem(courseId="CSE-3901", sectionId="002")],
        favorite=True,
    )

@schedule_router.put(
    "/save/{userId}",
    response_model=ScheduleSaved,
    status_code=status.HTTP_201_CREATED,
    summary="Saves a schedule",
)
async def save_schedule(userId: str, body: SchedulePayload):
    # TODO: upsert schedule
    return ScheduleSaved(
        scheduleId="sch_new",
        userId=userId,
        name=body.name or "Untitled",
        items=body.items,
        favorite=body.favorite,
    )

@schedule_router.post(
    "/add/{userId}",
    response_model=ScheduleSaved,
    status_code=status.HTTP_201_CREATED,
    summary="Add a schedule",
)
async def add_schedule(userId: str, body: SchedulePayload):
    # TODO: insert new schedule
    return ScheduleSaved(
        scheduleId="sch_added",
        userId=userId,
        name=body.name or "Untitled",
        items=body.items,
        favorite=body.favorite,
    )

# Added: delete schedule
@schedule_router.delete(
    "/{userId}/{scheduleId}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a schedule",
)
async def delete_schedule(userId: str, scheduleId: str):
    # TODO: delete in Postgres; 404 if not found
    return

# =======================
# USERS
# =======================

@users_router.post(
    "/",
    response_model=User,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new user",
)
async def create_user(user: UserCreate):
    # TODO: persist & hash password
    return User(id=1, username=user.username, email=user.email)

@users_router.get(
    "/{userId}",
    response_model=User,
    summary="Get a user by ID",
)
async def get_user(userId: int):
    # TODO: fetch from Postgres
    return User(id=userId, username="sample", email="sample@example.com")

@users_router.put(
    "/{userId}",
    response_model=User,
    summary="Update a user by ID",
)
async def update_user(userId: int, user: UserUpdate):
    # TODO: partial update
    return User(id=userId, username=user.username or "sample", email=user.email or "sample@example.com")

@users_router.delete(
    "/{userId}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a user by ID",
)
async def delete_user(userId: int):
    # TODO: delete; 404 if not found
    return

# =======================
# Helper to attach to FastAPI app
# =======================
#def include_all_routers(app):
    """
    In main.py:
        from routers import include_all_routers
        include_all_routers(app)
    """
   # app.include_router(courses_router)
   # app.include_router(schedule_router)
   # app.include_router(users_router)
