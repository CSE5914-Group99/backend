"""Schema package exports for convenient imports."""

from .course import CompareItem, CourseRating, CoursesCompareRequest, CoursesCompareResult
from .schedule import (
    Course,
    Event,
    Schedule,
    ScheduleLoadRequest,
    ScheduleLoadResult,
    SchedulePayload,
)
from .user import LoginRequest, Token, User, UserCreate, UserExists, UserUpdate

__all__ = [
    "CompareItem",
    "CourseRating",
    "CoursesCompareRequest",
    "CoursesCompareResult",
    "Course",
    "Event",
    "Schedule",
    "ScheduleLoadRequest",
    "ScheduleLoadResult",
    "SchedulePayload",
    "LoginRequest",
    "Token",
    "User",
    "UserCreate",
    "UserExists",
    "UserUpdate",
]
