from __future__ import annotations

from typing import Any, Dict, List, Optional, Literal
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

# DayOfWeek type matching frontend
DayOfWeek = Literal['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']


class Course(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    courseId: str
    id: Optional[str | int] = None  # Changed to allow string IDs (e.g. "CSE 2221")
    title: Optional[str] = None
    instructor: Optional[str] = None
    startTime: Optional[str] = None  # HH:mm format
    endTime: Optional[str] = None    # HH:mm format
    type: Optional[str] = None
    difficultyRating: Optional[float] = None
    mode: Optional[str] = None
    session: Optional[int] = None
    repeatDays: Optional[List[DayOfWeek]] = None
    campus: Optional[str] = None
    semester: Optional[str] = None
    status: Optional[str] = None
    
    # Full grading details from the agent
    ratingDetails: Optional[Dict[str, Any]] = None


class Event(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: Optional[int] = None
    title: str
    description: Optional[str] = None
    startTime: Optional[str] = None
    endTime: Optional[str] = None
    repeatDays: Optional[List[DayOfWeek]] = None
    campus: Optional[str] = None
    semester: Optional[str] = None


class Schedule(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: Optional[int] = None
    name: str
    favorite: bool
    campus: Optional[str] = None
    semester: Optional[str] = None
    courses: List[Course] = Field(default_factory=list)
    events: List[Event] = Field(default_factory=list)
    difficultyScore: Optional[float] = None
    weeklyHours: Optional[float] = None
    creditHours: Optional[float] = None
    createdAt: Optional[datetime] = None
    updatedAt: Optional[datetime] = None


# Legacy/Payload models to support creation if needed, or we can use Schedule
# But for creation, we might receive a slightly different structure (e.g. without IDs)
# Let's keep SchedulePayload but align it with Schedule if possible, or map it.
# The frontend sends SchedulePayload which has items/activities.
# We should probably update the frontend to send 'courses' and 'events' too, 
# but if we can't change frontend code easily, we should keep SchedulePayload 
# but maybe map it to Schedule internally.
# However, the user said "change the backend models... cause no confusion".
# So I will update SchedulePayload to match the frontend's SchedulePayload interface 
# (which was shown in previous context, but maybe I should align it with the new Schedule model).
# The screenshot shows `Schedule` interface. It doesn't show `SchedulePayload`.
# I will assume the frontend uses `Schedule` for everything now.

class SchedulePayload(BaseModel):
    scheduleId: Optional[int] = None
    id: Optional[int] = None  # Alias for scheduleId to support frontend sending 'id'
    name: str
    favorite: bool
    campus: Optional[str] = None
    semester: Optional[str] = None
    courses: List[Course] = Field(default_factory=list)
    events: List[Event] = Field(default_factory=list)
    # Support legacy fields if frontend still sends them
    items: Optional[List[Any]] = None 
    activities: Optional[List[Any]] = None


class ScheduleLoadRequest(BaseModel):
    courseIds: List[str]
    constraints: Optional[Dict[str, Any]] = Field(
        default_factory=lambda: {"maxCredits": 18, "noFri": False}
    )


class ScheduleLoadResult(BaseModel):
    weeklyHours: float
    byCourse: Dict[str, float]
