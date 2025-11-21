from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from db import (
    Schedule as ScheduleORM,
    ScheduleActivity as ScheduleActivityORM,
    Course as CourseORM,
    User as UserORM,
    get_session,
)
from schemas import (
    Schedule,
    SchedulePayload,
    Course as CourseSchema,
)

schedule_router = APIRouter(prefix="/schedule", tags=["schedule"])


def _compute_difficulty(schedule: ScheduleORM) -> float:
    """Compute difficulty score server-side without persisting it.
    Simple heuristic: number of items; adjust as needed.
    """
    try:
        return float(len(schedule.section_ids or []))
    except Exception:
        return 0.0


def _format_times_days(repeat_days: list[str] | None, start_time: str | None, end_time: str | None) -> str | None:
    if not start_time or not end_time:
        return None
    days_str = ", ".join(repeat_days) if repeat_days else ""
    return f"{days_str} {start_time}-{end_time}".strip()


async def _ensure_user_exists(google_uid: str, session: AsyncSession) -> str:
    user_uid = await session.scalar(select(UserORM.google_uid).where(UserORM.google_uid == google_uid))
    if not user_uid:
        raise HTTPException(status_code=404, detail="User not found")
    return user_uid


async def _upsert_courses(courses_payload: list[CourseSchema], session: AsyncSession) -> list[str]:
    """Upsert courses into the shared Course table and return their IDs."""
    course_ids = []
    for item in courses_payload:
        # Determine ID: Section ID (if number) or Course ID (if string)
        # Logic: if session is present, use it as ID. Else use courseId.
        # Wait, user said: "if the string is a full integer(number) then it is a secion if iit is a string then it is a course with no section"
        # So we should check item.session first.
        
        if item.session:
            c_id = str(item.session)
        else:
            c_id = item.courseId
            
        course_ids.append(c_id)

        # Check if course exists
        existing = await session.get(CourseORM, c_id)
        if existing:
            # Update fields if needed (optional, but good for keeping data fresh)
            existing.title = item.title or existing.title
            existing.teacher_name = item.instructor or existing.teacher_name
            existing.times_days = _format_times_days(item.repeatDays, item.startTime, item.endTime)
            existing.campus = item.campus or existing.campus
            existing.semester = item.semester or existing.semester
            existing.type = item.type or existing.type
            existing.difficulty_rating = item.difficultyRating or existing.difficulty_rating
            existing.mode = item.mode or existing.mode
            existing.status = item.status or existing.status
            if item.ratingDetails:
                existing.rating_details = item.ratingDetails
        else:
            # Create new
            new_course = CourseORM(
                id=c_id,
                course_id=item.courseId,
                title=item.title or "Untitled Course",
                teacher_name=item.instructor or "unknown",
                section_id=str(item.session) if item.session else None,
                times_days=_format_times_days(item.repeatDays, item.startTime, item.endTime),
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


async def _attach_courses_to_schedules(schedules: list[ScheduleORM], session: AsyncSession):
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


@schedule_router.get(
    "/{google_uid}",
    response_model=list[Schedule],
    summary="Gets all of the user's saved schedules",
)
async def get_user_schedules(
    google_uid: str, session: AsyncSession = Depends(get_session)
):
    user_id = await _ensure_user_exists(google_uid, session)
    result = await session.execute(
        select(ScheduleORM)
        .options(
            selectinload(ScheduleORM.activities),
        )
        .where(ScheduleORM.user_id == user_id)
        .order_by(ScheduleORM.created_at.desc())
    )
    schedules = result.scalars().all()
    
    # Populate courses manually
    await _attach_courses_to_schedules(schedules, session)
    
    return schedules


@schedule_router.get(
    "/favorite/{google_uid}",
    response_model=Schedule | None,
    summary="Gets the user's favorite schedule",
)
async def get_favorite_schedule(
    google_uid: str, session: AsyncSession = Depends(get_session)
):
    user_id = await _ensure_user_exists(google_uid, session)
    result = await session.execute(
        select(ScheduleORM)
        .options(
            selectinload(ScheduleORM.activities),
        )
        .where(ScheduleORM.user_id == user_id, ScheduleORM.is_starred.is_(True))
        .limit(1)
    )
    schedule = result.scalars().first()
    
    if schedule:
        await _attach_courses_to_schedules([schedule], session)
        
    return schedule


@schedule_router.post(
    "/add/{google_uid}",
    response_model=Schedule,
    status_code=status.HTTP_201_CREATED,
    summary="Add a schedule",
)
async def add_schedule(
    google_uid: str, body: SchedulePayload, session: AsyncSession = Depends(get_session)
):
    user_id = await _ensure_user_exists(google_uid, session)
    favorite_flag = body.favorite if body.favorite is not None else False
    
    # Upsert courses and get IDs
    courses_payload = body.courses or []
    section_ids = await _upsert_courses(courses_payload, session)

    events_payload = body.events or []
    activities: list[ScheduleActivityORM] = [
        ScheduleActivityORM(
            title=event.title,
            description=event.description,
            times_days=_format_times_days(event.repeatDays, event.startTime, event.endTime),
            campus=event.campus,
            semester=event.semester,
        )
        for event in events_payload
    ]

    # Construct schedule
    schedule = ScheduleORM(
        user_id=user_id,
        name=body.name or "Untitled",
        is_starred=favorite_flag,
        campus=body.campus,
        semester=body.semester,
        section_ids=section_ids,
        activities=activities,
    )

    session.add(schedule)
    await session.flush()

    if favorite_flag:
        await session.execute(
            update(ScheduleORM)
            .where(ScheduleORM.user_id == user_id, ScheduleORM.id != schedule.id)
            .values(is_starred=False)
        )

    await session.commit()

    # Re-load and attach courses
    result = await session.execute(
        select(ScheduleORM)
        .options(
            selectinload(ScheduleORM.activities),
        )
        .where(ScheduleORM.id == schedule.id)
    )
    schedule_loaded = result.scalars().first()
    if schedule_loaded:
        await _attach_courses_to_schedules([schedule_loaded], session)
        
    return schedule_loaded or schedule


@schedule_router.put(
    "/save/{google_uid}",
    response_model=Schedule,
    summary="Saves (updates) a schedule",
)
async def save_schedule(
    google_uid: str, body: SchedulePayload, session: AsyncSession = Depends(get_session)
):
    schedule_id = body.scheduleId or body.id
    if not schedule_id:
        raise HTTPException(status_code=400, detail="scheduleId is required to update")

    user_id = await _ensure_user_exists(google_uid, session)
    result = await session.execute(
        select(ScheduleORM)
        .options(
            selectinload(ScheduleORM.activities),
        )
        .where(ScheduleORM.id == schedule_id, ScheduleORM.user_id == user_id)
    )
    schedule = result.scalars().first()
    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")

    if body.name:
        schedule.name = body.name
    
    if body.campus:
        schedule.campus = body.campus
    
    if body.semester:
        schedule.semester = body.semester

    if body.courses is not None:
        # Upsert courses and update IDs list
        section_ids = await _upsert_courses(body.courses, session)
        schedule.section_ids = section_ids

    if body.events is not None:
        # Replace activities via direct table ops
        await session.execute(
            delete(ScheduleActivityORM).where(ScheduleActivityORM.schedule_id == schedule.id)
        )
        
        new_activities = [
            ScheduleActivityORM(
                schedule_id=schedule.id,
                title=event.title,
                description=event.description,
                times_days=_format_times_days(event.repeatDays, event.startTime, event.endTime),
                campus=event.campus,
                semester=event.semester,
            )
            for event in body.events
        ]
        session.add_all(new_activities)

    if body.favorite is not None:
        schedule.is_starred = body.favorite

    if schedule.is_starred:
        await session.execute(
            update(ScheduleORM)
            .where(ScheduleORM.user_id == user_id, ScheduleORM.id != schedule.id)
            .values(is_starred=False)
        )

    await session.commit()
    await session.refresh(schedule)
    
    # Attach courses for response
    await _attach_courses_to_schedules([schedule], session)
    
    return schedule


@schedule_router.delete(
    "/{google_uid}/{scheduleId}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a schedule",
)
async def delete_schedule(
    google_uid: str, scheduleId: int, session: AsyncSession = Depends(get_session)
):
    user_id = await _ensure_user_exists(google_uid, session)
    schedule = await session.scalar(
        select(ScheduleORM).where(
            ScheduleORM.id == scheduleId, ScheduleORM.user_id == user_id
        )
    )
    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")

    await session.delete(schedule)
    await session.commit()


@schedule_router.get(
    "/{google_uid}/{scheduleId}",
    response_model=Schedule,
    summary="Get a specific schedule",
)
async def get_schedule(
    google_uid: str, scheduleId: int, session: AsyncSession = Depends(get_session)
):
    user_id = await _ensure_user_exists(google_uid, session)
    result = await session.execute(
        select(ScheduleORM)
        .options(
            selectinload(ScheduleORM.activities),
        )
        .where(ScheduleORM.id == scheduleId, ScheduleORM.user_id == user_id)
    )
    schedule = result.scalars().first()
    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")
    
    await _attach_courses_to_schedules([schedule], session)
    
    return schedule
