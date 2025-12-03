from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db import (
    Schedule as ScheduleORM,
    Course as CourseORM,
    User as UserORM,
)
from schemas import (
    Course as CourseSchema,
)

def compute_difficulty(schedule: ScheduleORM) -> float:
    """Compute difficulty score server-side without persisting it.
    Simple heuristic: number of items; adjust as needed.
    """
    try:
        return float(len(schedule.section_ids or []))
    except Exception:
        return 0.0


def format_times_days(repeat_days: list[str] | None, start_time: str | None, end_time: str | None) -> str | None:
    if not start_time or not end_time:
        return None
    days_str = ", ".join(repeat_days) if repeat_days else ""
    return f"{days_str} {start_time}-{end_time}".strip()


def filter_redundant_courses(courses: list[CourseSchema]) -> list[CourseSchema]:
    """
    Filter out redundant course entries.
    1. If a course is present as both a generic course (no session) and a specific section (with session),
       remove the generic one.
    2. Deduplicate identical entries.
    """
    if not courses:
        return []

    # Group by courseId (normalized)
    by_id: dict[str, list[CourseSchema]] = {}
    for c in courses:
        # Normalize ID for grouping
        cid = c.courseId.strip().upper() if c.courseId else ""
        if not cid:
            continue
        if cid not in by_id:
            by_id[cid] = []
        by_id[cid].append(c)
    
    final_list = []
    for cid, items in by_id.items():
        has_session = any(item.session for item in items)
        if has_session:
            # Keep only those with session
            # Also deduplicate by session ID to avoid same section appearing twice
            seen_sessions = set()
            for item in items:
                if item.session and item.session not in seen_sessions:
                    final_list.append(item)
                    seen_sessions.add(item.session)
        else:
            # Keep only one generic entry
            final_list.append(items[0])
            
    return final_list


async def ensure_user_exists(google_uid: str, session: AsyncSession) -> str:
    user_uid = await session.scalar(select(UserORM.google_uid).where(UserORM.google_uid == google_uid))
    if not user_uid:
        raise HTTPException(status_code=404, detail="User not found")
    return user_uid


async def upsert_courses(courses_payload: list[CourseSchema], session: AsyncSession) -> list[str]:
    """Upsert courses into the shared Course table and return their IDs."""
    course_ids = []
    for item in courses_payload:
        # Normalize courseId
        if item.courseId:
            item.courseId = item.courseId.strip() # Keep case for display? Or upper? 
            pass

        # Determine ID: Section ID (if number) or Course ID (if string)
        if item.session:
            c_id = str(item.session)
        else:
            # Use normalized course ID for the primary key to avoid duplicates like "CSE 2331" vs "cse 2331"
            c_id = item.courseId.strip().upper() if item.courseId else "UNKNOWN"
            
        course_ids.append(c_id)

        # Check if course exists
        existing = await session.get(CourseORM, c_id)
        if existing:
            # Update fields if needed (optional, but good for keeping data fresh)
            existing.title = item.title or existing.title
            existing.teacher_name = item.instructor or existing.teacher_name
            existing.times_days = format_times_days(item.repeatDays, item.startTime, item.endTime)
            existing.campus = item.campus or existing.campus
            existing.semester = item.semester or existing.semester
            existing.type = item.type or existing.type
            existing.mode = item.mode or existing.mode
            existing.status = item.status or existing.status
            
            # Always update difficulty rating and details if provided
            if item.difficultyRating is not None:
                existing.difficulty_rating = item.difficultyRating
            
            if item.ratingDetails:
                existing.rating_details = item.ratingDetails
        else:
            # Create new
            new_course = CourseORM(
                id=c_id,
                course_id=item.courseId, # Keep original casing for display
                title=item.title or "Untitled Course",
                teacher_name=item.instructor or "unknown",
                section_id=str(item.session) if item.session else None,
                times_days=format_times_days(item.repeatDays, item.startTime, item.endTime),
                campus=item.campus,
                semester=item.semester,
                type=item.type,
                difficulty_rating=item.difficultyRating,
                mode=item.mode,
                status=item.status,
                rating_details=item.ratingDetails,
            )
            session.add(new_course)
    
    await session.flush()
    return course_ids


async def attach_courses_to_schedules(schedules: list[ScheduleORM], session: AsyncSession):
    """Manually populate the .courses property for a list of schedules."""
    for schedule in schedules:
        if not schedule.section_ids:
            schedule.courses = []
            continue
        
        # Fetch all courses for this schedule
        # We can optimize this to fetch all needed courses in one query if needed, 
        # but for now per-schedule fetch is simpler.
        result = await session.execute(
            select(CourseORM).where(CourseORM.id.in_(schedule.section_ids))
        )
        schedule.courses = result.scalars().all()
