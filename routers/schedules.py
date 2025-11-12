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
    ScheduleActivity,
    ScheduleCourseDetail,
    SchedulePayload,
    ScheduleSaved,
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


def _map_schedule(schedule: ScheduleORM) -> ScheduleSaved:
    return ScheduleSaved(
        scheduleId=schedule.id,
        userId=schedule.user_id,
        name=schedule.name,
        favorite=schedule.is_starred,
        difficultyScore=_compute_difficulty(schedule),
        items=[
            ScheduleCourseDetail(
                courseId=item.course_id,
                sectionId=item.section_id,
                timesDays=item.times_days,
            )
            for item in schedule.detailed_courses
        ],
        activities=[
            ScheduleActivity(description=activity.description, timesDays=activity.times_days)
            for activity in schedule.activities
        ],
    )


async def _ensure_user_exists(user_id: int, session: AsyncSession) -> None:
    exists = await session.scalar(select(UserORM.id).where(UserORM.id == user_id))
    if not exists:
        raise HTTPException(status_code=404, detail="User not found")


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
    "/{userId}",
    response_model=list[ScheduleSaved],
    summary="Gets all of the user's saved schedules",
)
async def get_user_schedules(
    userId: int, session: AsyncSession = Depends(get_session)
):
    await _ensure_user_exists(userId, session)
    result = await session.execute(
        select(ScheduleORM)
        .options(
            selectinload(ScheduleORM.detailed_courses),
            selectinload(ScheduleORM.activities),
        )
        .where(ScheduleORM.user_id == userId)
        .order_by(ScheduleORM.created_at.desc())
    )
    schedules = result.scalars().all()
    return [_map_schedule(schedule) for schedule in schedules]


@schedule_router.get(
    "/favorite/{userId}",
    response_model=ScheduleSaved | None,
    summary="Gets the user's favorite schedule",
)
async def get_favorite_schedule(
    userId: int, session: AsyncSession = Depends(get_session)
):
    await _ensure_user_exists(userId, session)
    result = await session.execute(
        select(ScheduleORM)
        .options(
            selectinload(ScheduleORM.detailed_courses),
            selectinload(ScheduleORM.activities),
        )
        .where(ScheduleORM.user_id == userId, ScheduleORM.is_starred.is_(True))
        .limit(1)
    )
    schedule = result.scalars().first()
    if not schedule:
        return None
    return _map_schedule(schedule)


@schedule_router.post(
    "/add/{userId}",
    response_model=ScheduleSaved,
    status_code=status.HTTP_201_CREATED,
    summary="Add a schedule",
)
async def add_schedule(
    userId: int, body: SchedulePayload, session: AsyncSession = Depends(get_session)
):
    await _ensure_user_exists(userId, session)
    favorite_flag = body.favorite if body.favorite is not None else False
    # Resolve courses up front (awaits before building children to avoid later lazy loads)
    items_payload = body.items or []
    pre_resolved: list[tuple[str, str]] = []  # (course_id, teacher_name)
    for item in items_payload:
        teacher_name = getattr(item, "teacherName", None) or "unknown"
        await _get_or_create_course(item.courseId, session, teacher_name)
        pre_resolved.append((item.courseId, teacher_name))

    # Build child objects fully in-memory with no awaits
    detailed_courses: list[ScheduleCourseORM] = [
        ScheduleCourseORM(
            course_id=cid,
            teacher_name=tname,
            section_id=item.sectionId,
            times_days=item.timesDays,
        )
        for (cid, tname), item in zip(pre_resolved, items_payload)
    ]

    activities_payload = body.activities or []
    activities: list[ScheduleActivityORM] = [
        ScheduleActivityORM(
            description=activity.description,
            times_days=activity.timesDays,
        )
        for activity in activities_payload
    ]

    # Construct schedule with relationships assigned before adding to session
    schedule = ScheduleORM(
        user_id=userId,
        name=body.name or "Untitled",
        is_starred=favorite_flag,
        detailed_courses=detailed_courses,
        activities=activities,
    )

    session.add(schedule)
    await session.flush()

    if favorite_flag:
        await session.execute(
            update(ScheduleORM)
            .where(ScheduleORM.user_id == userId, ScheduleORM.id != schedule.id)
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
    return _map_schedule(schedule_loaded or schedule)


@schedule_router.put(
    "/save/{userId}",
    response_model=ScheduleSaved,
    summary="Saves (updates) a schedule",
)
async def save_schedule(
    userId: int, body: SchedulePayload, session: AsyncSession = Depends(get_session)
):
    if not body.scheduleId:
        raise HTTPException(status_code=400, detail="scheduleId is required to update")

    await _ensure_user_exists(userId, session)
    result = await session.execute(
        select(ScheduleORM)
        .options(
            selectinload(ScheduleORM.detailed_courses),
            selectinload(ScheduleORM.activities),
        )
        .where(ScheduleORM.id == body.scheduleId, ScheduleORM.user_id == userId)
    )
    schedule = result.scalars().first()
    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")

    if body.name:
        schedule.name = body.name

    if body.items is not None:
        # Resolve courses first
        resolved_items: list[ScheduleCourseORM] = []
        for item in body.items:
            teacher_name = getattr(item, "teacherName", None) or "unknown"
            await _get_or_create_course(item.courseId, session, teacher_name)
            resolved_items.append(
                ScheduleCourseORM(
                    schedule_id=schedule.id,
                    course_id=item.courseId,
                    teacher_name=teacher_name,
                    section_id=item.sectionId,
                    times_days=item.timesDays,
                )
            )

        # Replace children via direct table ops to avoid lazy-loading collections
        await session.execute(
            delete(ScheduleCourseORM).where(ScheduleCourseORM.schedule_id == schedule.id)
        )
        session.add_all(resolved_items)

    if body.activities is not None:
        # Replace activities via direct table ops
        await session.execute(
            delete(ScheduleActivityORM).where(ScheduleActivityORM.schedule_id == schedule.id)
        )
        session.add_all(
            [
                ScheduleActivityORM(
                    schedule_id=schedule.id,
                    description=activity.description,
                    times_days=activity.timesDays,
                )
                for activity in body.activities
            ]
        )

    if body.favorite is not None:
        schedule.is_starred = body.favorite

    if schedule.is_starred:
        await session.execute(
            update(ScheduleORM)
            .where(ScheduleORM.user_id == userId, ScheduleORM.id != schedule.id)
            .values(is_starred=False)
        )

    await session.commit()
    await session.refresh(schedule)
    return _map_schedule(schedule)


@schedule_router.delete(
    "/{userId}/{scheduleId}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a schedule",
)
async def delete_schedule(
    userId: int, scheduleId: int, session: AsyncSession = Depends(get_session)
):
    await _ensure_user_exists(userId, session)
    schedule = await session.scalar(
        select(ScheduleORM).where(
            ScheduleORM.id == scheduleId, ScheduleORM.user_id == userId
        )
    )
    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")

    await session.delete(schedule)
    await session.commit()
