from .course_search import course_search_router
from .courses import courses_router
from .rate_my_professor import rate_my_professor_router
from .schedules import schedule_router
from .users import users_router

__all__ = [
	"course_search_router",
	"courses_router",
	"rate_my_professor_router",
	"schedule_router",
	"users_router",
]
