from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, Body
from langchain_core.messages import HumanMessage
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from agents.class_grading_agent import ClassScore, class_grading_graph
from agents.schedule_grading_agent import ClassTeacherTuple, ScheduleScore, schedule_grading_graph
from db.session import get_session

courses_router = APIRouter(prefix="/courses", tags=["courses"])

@courses_router.get("/ratings/{courseId}", response_model=ClassScore)
async def ratings_courseId(
    courseId: str,
    teacher_name: str | None = None,
    session: AsyncSession = Depends(get_session)
):
    # 1. Without teacher name: /courses/ratings/CSE2331
    # 2. With teacher name: /courses/ratings/CSE2331?teacher_name=John%20Doe
    courseId = courseId.replace(" ", "").lower()
    teacher_name_id_form = teacher_name.replace(" ", "").lower() if teacher_name else 'unknown'

    # Include teacher name in the message if provided
    if teacher_name and teacher_name != 'unknown':
        message_content = f"Evaluate the class {courseId} taught by Professor {teacher_name}"
    else:
        message_content = f"Evaluate the class {courseId} (no specific instructor provided)"

    test_messages = [HumanMessage(content=message_content)]
    initial_state = {
        "messages": test_messages,
        "class_name": courseId,
        "teacher_name": teacher_name_id_form,
        "class_score": None,
        "cached": False,
        "session": session,  # Pass session for database caching
    }
    result = await class_grading_graph.ainvoke(initial_state)
    return result["class_score"]

# Request model for schedule-load endpoint
class ScheduleLoadRequest(BaseModel):
    courses: List[ClassTeacherTuple]
    user_id: int
    constraints: str | None = None
@courses_router.post("/schedule-load", response_model=ScheduleScore)
async def schedule_load(
    request: ScheduleLoadRequest,
    session: AsyncSession = Depends(get_session)
):
    """
    Score a complete schedule of classes.
    Takes a list of class/teacher tuples and returns a comprehensive schedule analysis
    including individual class scores and overall schedule difficulty metrics.

    The scored schedule will be saved to the database and associated with the user.
    """
    initial_state = {
        "schedule": request.courses,
        "schedule_score": None,
        "messages": [],
        "user_id": request.user_id,
        "constraints": request.constraints,
        "schedule_id": None,
        "session": session
    }

    # Run the schedule grading graph
    result = await schedule_grading_graph.ainvoke(initial_state)

    # Return the complete schedule score object
    return result["schedule_score"]


@courses_router.post("/compare", response_model=List[ClassScore])
async def compare(courseIds: List[str]):
    return
