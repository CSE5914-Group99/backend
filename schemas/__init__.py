"""Schema package exports for convenient imports."""

from .course import CompareItem, CourseRating, CoursesCompareRequest, CoursesCompareResult
from .schedule import (
    ScheduleActivity,
    ScheduleCourseDetail,
    ScheduleLoadRequest,
    ScheduleLoadResult,
    SchedulePayload,
    ScheduleSaved,
)
from .user import LoginRequest, Token, User, UserCreate, UserUpdate

__all__ = [
    "CompareItem",
    "CourseRating",
    "CoursesCompareRequest",
    "CoursesCompareResult",
    "ScheduleActivity",
    "ScheduleCourseDetail",
    "ScheduleLoadRequest",
    "ScheduleLoadResult",
    "SchedulePayload",
    "ScheduleSaved",
    "LoginRequest",
    "Token",
    "User",
    "UserCreate",
    "UserUpdate",
]
