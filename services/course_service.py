from __future__ import annotations

from typing import List

from langchain_core.messages import HumanMessage
from sqlalchemy.ext.asyncio import AsyncSession

from agents.class_grading_agent import ClassScore, class_grading_graph
from agents.schedule_grading_agent import ClassTeacherTuple, ScheduleScore, schedule_grading_graph
from agents.class_recommender_agent import (
    ScheduleClassWithTime,
    ModificationRequest,
    RecommenderOutput,
    class_recommender_graph
)


async def get_course_rating(
    course_id: str,
    teacher_name: str | None,
    session: AsyncSession
) -> ClassScore:
    # 1. Without teacher name: /courses/ratings/CSE2331
    # 2. With teacher name: /courses/ratings/CSE2331?teacher_name=John%20Doe
    course_id = course_id.replace(" ", "").lower()
    teacher_name_id_form = teacher_name.replace(" ", "").lower() if teacher_name else 'unknown'

    # Include teacher name in the message if provided
    if teacher_name and teacher_name != 'unknown':
        message_content = f"Evaluate the class {course_id} taught by Professor {teacher_name}"
    else:
        message_content = f"Evaluate the class {course_id} (no specific instructor provided)"

    test_messages = [HumanMessage(content=message_content)]
    initial_state = {
        "messages": test_messages,
        "class_name": course_id,
        "teacher_name": teacher_name_id_form,
        "class_score": None,
        "cached": False,
        "session": session,  # Pass session for database caching
    }
    result = await class_grading_graph.ainvoke(initial_state)
    return result["class_score"]


async def grade_schedule(
    courses: List[ClassTeacherTuple],
    constraints: str | None,
    session: AsyncSession
) -> ScheduleScore:
    """
    Score a complete schedule of classes.
    Takes a list of class/teacher tuples and returns a comprehensive schedule analysis
    including individual class scores and overall schedule difficulty metrics.
    """
    initial_state = {
        "schedule": courses,
        "schedule_score": None,
        "messages": [],
        "constraints": constraints,
        "session": session
    }

    # Run the schedule grading graph
    result = await schedule_grading_graph.ainvoke(initial_state)

    # Return the complete schedule score object
    return result["schedule_score"]


async def get_class_recommendations(
    schedule: List[ScheduleClassWithTime],
    schedule_score: ScheduleScore,
    modification_requests: List[ModificationRequest],
    session: AsyncSession
) -> RecommenderOutput:
    """
    Get class recommendations for modifying a schedule.
    """
    initial_state = {
        "messages": [],
        "schedule": schedule,
        "schedule_score": schedule_score,
        "modification_requests": modification_requests,
        "alternatives_found": None,
        "feasible_alternatives": None,
        "graded_alternatives": {},
        "recommender_output": None,
        "session": session
    }

    # Run the class recommender graph
    result = await class_recommender_graph.ainvoke(initial_state)

    return result["recommender_output"]
