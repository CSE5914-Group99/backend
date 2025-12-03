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
from services.schedule_service import (
    ensure_user_exists,
    upsert_courses,
    attach_courses_to_schedules,
    format_times_days,
    filter_redundant_courses,
)

schedule_router = APIRouter(prefix="/schedule", tags=["schedule"])


@schedule_router.get(
    "/{google_uid}",
    response_model=list[Schedule],
    summary="Gets all of the user's saved schedules",
)
async def get_user_schedules(
    google_uid: str, session: AsyncSession = Depends(get_session)
):
    user_id = await ensure_user_exists(google_uid, session)
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
    await attach_courses_to_schedules(schedules, session)
    
    return schedules


@schedule_router.get(
    "/favorite/{google_uid}",
    response_model=Schedule | None,
    summary="Gets the user's favorite schedule",
)
async def get_favorite_schedule(
    google_uid: str, session: AsyncSession = Depends(get_session)
):
    user_id = await ensure_user_exists(google_uid, session)
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
        await attach_courses_to_schedules([schedule], session)
        
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
    user_id = await ensure_user_exists(google_uid, session)
    favorite_flag = body.favorite if body.favorite is not None else False
    
    # Upsert courses and get IDs
    courses_payload = body.courses or []
    courses_payload = filter_redundant_courses(courses_payload)
    section_ids = await upsert_courses(courses_payload, session)

    events_payload = body.events or []
    activities: list[ScheduleActivityORM] = [
        ScheduleActivityORM(
            title=event.title,
            description=event.description,
            times_days=format_times_days(event.repeatDays, event.startTime, event.endTime),
            campus=event.campus,
            semester=event.semester,
        )
        for event in events_payload
    ]

    # Prepare grading details
    # Ensure weeklyHours is saved into grading_details as time_load
    grading_details = body.gradingDetails or {}
    if body.weeklyHours is not None:
        grading_details['time_load'] = body.weeklyHours

    # Construct schedule
    schedule = ScheduleORM(
        user_id=user_id,
        name=body.name or "Untitled",
        is_starred=favorite_flag,
        campus=body.campus,
        semester=body.semester,
        section_ids=section_ids,
        activities=activities,
        grading_details=grading_details,
        total_credit_hours=int(body.creditHours) if body.creditHours is not None else None,
        difficulty_score=float(body.difficultyScore) if body.difficultyScore is not None else None,
        num_classes=len(courses_payload),
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
        await attach_courses_to_schedules([schedule_loaded], session)
        
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

    user_id = await ensure_user_exists(google_uid, session)
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
        courses_payload = filter_redundant_courses(body.courses)
        section_ids = await upsert_courses(courses_payload, session)
        schedule.section_ids = section_ids
        # Update num_classes based on filtered list
        schedule.num_classes = len(courses_payload)

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
                times_days=format_times_days(event.repeatDays, event.startTime, event.endTime),
                campus=event.campus or body.campus, # Fallback to schedule campus if not on event
                semester=event.semester or body.semester, # Fallback to schedule semester if not on event
            )
            for event in body.events
        ]
        session.add_all(new_activities)

    if body.favorite is not None:
        schedule.is_starred = body.favorite

    if body.gradingDetails is not None:
        schedule.grading_details = body.gradingDetails

    # Update top-level metrics if provided
    if body.creditHours is not None:
        schedule.total_credit_hours = int(body.creditHours)
    
    if body.difficultyScore is not None:
        schedule.difficulty_score = float(body.difficultyScore)

    # Note: weeklyHours is derived from grading_details['time_load'] in the model property,
    # but if we want to persist it explicitly or if grading_details is missing, we might need a column.
    # However, the model currently only has total_credit_hours and num_classes as explicit columns.
    # weeklyHours is a property. So we rely on grading_details for weeklyHours.
    # But we should ensure grading_details has time_load if weeklyHours is provided.
    if body.weeklyHours is not None:
        # Update time_load in grading_details if it exists
        # We need to create a new dict to ensure SQLAlchemy detects the change
        details = dict(schedule.grading_details) if schedule.grading_details else {}
        details['time_load'] = body.weeklyHours
        schedule.grading_details = details

    if schedule.is_starred:
        await session.execute(
            update(ScheduleORM)
            .where(ScheduleORM.user_id == user_id, ScheduleORM.id != schedule.id)
            .values(is_starred=False)
        )

    await session.commit()
    await session.refresh(schedule)
    
    # Attach courses for response
    await attach_courses_to_schedules([schedule], session)
    
    return schedule


@schedule_router.delete(
    "/{google_uid}/{scheduleId}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a schedule",
)
async def delete_schedule(
    google_uid: str, scheduleId: int, session: AsyncSession = Depends(get_session)
):
    user_id = await ensure_user_exists(google_uid, session)
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
    user_id = await ensure_user_exists(google_uid, session)
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
    
    await attach_courses_to_schedules([schedule], session)
    
    return schedule
