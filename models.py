from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


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