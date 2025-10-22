# routers.py
from fastapi import APIRouter, status
from typing import List, Optional, Dict, Any

# Use your existing user models
from models import User, UserCreate, UserUpdate

# ---------------------------------------------------------
# Local DTOs only for courses/schedules (not in models.py)
# ---------------------------------------------------------
from pydantic import BaseModel, Field

# --- Courses ---
class CourseRating(BaseModel):
    courseId: str
    overall: float = Field(ge=0, le=5)
    difficulty: float = Field(ge=0, le=5)
    workload_hours_per_week: float = Field(ge=0)

class CompareItem(BaseModel):
    courseId: str
    term: Optional[str] = None

class CoursesCompareRequest(BaseModel):
    courses: List[CompareItem]
    weights: Optional[Dict[str, float]] = Field(
        default_factory=lambda: {"difficulty": 0.5, "workload": 0.5}
    )

class CoursesCompareResult(BaseModel):
    rankedCourses: List[str]           # courseIds best → worst
    scores: Dict[str, float]           # courseId → composite score

class ScheduleLoadRequest(BaseModel):
    courseIds: List[str]
    constraints: Optional[Dict[str, Any]] = Field(
        default_factory=lambda: {"maxCredits": 18, "noFri": False}
    )

class ScheduleLoadResult(BaseModel):
    weeklyHours: float
    byCourse: Dict[str, float]         # courseId → hours/week

# --- Schedules ---
class ScheduleItem(BaseModel):
    courseId: str
    sectionId: Optional[str] = None

class SchedulePayload(BaseModel):
    name: Optional[str] = "Untitled"
    items: List[ScheduleItem]
    favorite: bool = False

class ScheduleSaved(BaseModel):
    scheduleId: str
    userId: str
    name: str
    items: List[ScheduleItem]
    favorite: bool

# ---------------------------------------------------------
# Routers
# ---------------------------------------------------------
courses_router  = APIRouter(prefix="/courses",  tags=["courses"])
schedule_router = APIRouter(prefix="/schedule", tags=["schedule"])
users_router    = APIRouter(prefix="/users",    tags=["users"])

# =======================
# COURSES
# =======================

@courses_router.get(
    "/ratings/{courseId}",
    response_model=CourseRating,
    summary="Get recent ratings for a course",
)
async def get_course_ratings(courseId: str):
    # TODO: fetch via orchestrator/cache
    return CourseRating(courseId=courseId, overall=4.3, difficulty=2.8, workload_hours_per_week=7.5)

@courses_router.post(
    "/compare",
    response_model=CoursesCompareResult,
    summary="Compare multiple courses on difficulty & workload",
)
async def compare_courses(body: CoursesCompareRequest):
    # TODO: compute composite scores
    scores = {c.courseId: 0.7 for c in body.courses}
    ranked = sorted(scores.keys(), key=scores.get, reverse=True)
    return CoursesCompareResult(rankedCourses=ranked, scores=scores)

@courses_router.post(
    "/schedule-load",
    response_model=ScheduleLoadResult,
    summary="Simulate overall weekly load using ratings (+ constraints)",
)
async def simulate_schedule_load(body: ScheduleLoadRequest):
    # TODO: real simulation logic
    per_course = {cid: 6.0 for cid in body.courseIds}
    return ScheduleLoadResult(weeklyHours=sum(per_course.values()), byCourse=per_course)

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

@schedule_router.post(
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
def include_all_routers(app):
    """
    In main.py:
        from routers import include_all_routers
        include_all_routers(app)
    """
    app.include_router(courses_router)
    app.include_router(schedule_router)
    app.include_router(users_router)
