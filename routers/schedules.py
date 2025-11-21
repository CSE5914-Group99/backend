from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from db import (
    Course as CourseORM,
    Schedule as ScheduleORM,
    ScheduleActivity as ScheduleActivityORM,
    ScheduleCourse as ScheduleCourseORM,
    User as UserORM,
    get_session,
)
from schemas import (
    Schedule,
    SchedulePayload,
)

schedule_router = APIRouter(prefix="/schedule", tags=["schedule"])


def _compute_difficulty(schedule: ScheduleORM) -> float:
    """Compute difficulty score server-side without persisting it.
    Simple heuristic: number of items; adjust as needed.
    """
    try:
        return float(len(schedule.detailed_courses or []))
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


async def _get_or_create_course(course_id: str, session: AsyncSession, teacher_name: str | None = None) -> CourseORM:
    """Fetch a Course by (course_id, teacher_name) unique pair or create if missing.

    teacher_name defaults to 'unknown' when not provided.
    """
    tn = teacher_name or "unknown"
    result = await session.execute(
        select(CourseORM).where(CourseORM.course_id == course_id, CourseORM.teacher_name == tn)
    )
    course = result.scalars().first()
    if course is None:
        # Provide a minimal default for required JSON field
        course = CourseORM(course_id=course_id, teacher_name=tn, course_rating={})
        session.add(course)
        await session.flush()
    return course


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
            selectinload(ScheduleORM.detailed_courses),
            selectinload(ScheduleORM.activities),
        )
        .where(ScheduleORM.user_id == user_id)
        .order_by(ScheduleORM.created_at.desc())
    )
    schedules = result.scalars().all()
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
            selectinload(ScheduleORM.detailed_courses),
            selectinload(ScheduleORM.activities),
        )
        .where(ScheduleORM.user_id == user_id, ScheduleORM.is_starred.is_(True))
        .limit(1)
    )
    schedule = result.scalars().first()
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
    
    # Use courses from payload
    courses_payload = body.courses or []
    
    pre_resolved: list[tuple[str, str]] = []  # (course_id, teacher_name)
    for item in courses_payload:
        teacher_name = item.instructor or "unknown"
        await _get_or_create_course(item.courseId, session, teacher_name)
        pre_resolved.append((item.courseId, teacher_name))

    # Build child objects fully in-memory with no awaits
    detailed_courses: list[ScheduleCourseORM] = [
        ScheduleCourseORM(
            course_id=cid,
            teacher_name=tname,
            section_id=str(item.session) if item.session else None,
            times_days=_format_times_days(item.repeatDays, item.startTime, item.endTime),
            campus=item.campus,
            semester=item.semester,
        )
        for (cid, tname), item in zip(pre_resolved, courses_payload)
    ]

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

    # Construct schedule with relationships assigned before adding to session
    schedule = ScheduleORM(
        user_id=user_id,
        name=body.name or "Untitled",
        is_starred=favorite_flag,
        campus=body.campus,
        semester=body.semester,
        detailed_courses=detailed_courses,
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

    # Re-load eagerly to build response without lazy loads
    result = await session.execute(
        select(ScheduleORM)
        .options(
            selectinload(ScheduleORM.detailed_courses),
            selectinload(ScheduleORM.activities),
        )
        .where(ScheduleORM.id == schedule.id)
    )
    schedule_loaded = result.scalars().first()
    return schedule_loaded or schedule


@schedule_router.put(
    "/save/{google_uid}",
    response_model=Schedule,
    summary="Saves (updates) a schedule",
)
async def save_schedule(
    google_uid: str, body: SchedulePayload, session: AsyncSession = Depends(get_session)
):
    if not body.scheduleId:
        raise HTTPException(status_code=400, detail="scheduleId is required to update")

    user_id = await _ensure_user_exists(google_uid, session)
    result = await session.execute(
        select(ScheduleORM)
        .options(
            selectinload(ScheduleORM.detailed_courses),
            selectinload(ScheduleORM.activities),
        )
        .where(ScheduleORM.id == body.scheduleId, ScheduleORM.user_id == user_id)
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
        # Resolve courses first
        resolved_items: list[ScheduleCourseORM] = []
        for item in body.courses:
            teacher_name = item.instructor or "unknown"
            await _get_or_create_course(item.courseId, session, teacher_name)
            resolved_items.append(
                ScheduleCourseORM(
                    schedule_id=schedule.id,
                    course_id=item.courseId,
                    teacher_name=teacher_name,
                    section_id=str(item.session) if item.session else None,
                    times_days=_format_times_days(item.repeatDays, item.startTime, item.endTime),
                    campus=item.campus,
                    semester=item.semester,
                )
            )

        # Replace children via direct table ops to avoid lazy-loading collections
        await session.execute(
            delete(ScheduleCourseORM).where(ScheduleCourseORM.schedule_id == schedule.id)
        )
        session.add_all(resolved_items)

    if body.events is not None:
        # Replace activities via direct table ops
        await session.execute(
            delete(ScheduleActivityORM).where(ScheduleActivityORM.schedule_id == schedule.id)
        )
        session.add_all(
            [
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
        )

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
