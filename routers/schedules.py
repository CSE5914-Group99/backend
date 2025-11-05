from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, update
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


def _map_schedule(schedule: ScheduleORM) -> ScheduleSaved:
    return ScheduleSaved(
        scheduleId=schedule.id,
        userId=schedule.user_id,
        name=schedule.name,
        favorite=schedule.is_starred,
        difficultyScore=schedule.difficulty_score,
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


async def _get_or_create_course(course_id: str, session: AsyncSession) -> CourseORM:
    course = await session.get(CourseORM, course_id)
    if course is None:
        course = CourseORM(id=course_id, name=course_id)
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
    difficulty = body.difficultyScore if body.difficultyScore is not None else 0.0
    schedule = ScheduleORM(
        user_id=userId,
        name=body.name or "Untitled",
        is_starred=favorite_flag,
        difficulty_score=difficulty,
    )

    session.add(schedule)
    await session.flush()

    items_payload = body.items or []
    detailed_courses: list[ScheduleCourseORM] = []
    for item in items_payload:
        await _get_or_create_course(item.courseId, session)
        detailed_courses.append(
            ScheduleCourseORM(
                schedule_id=schedule.id,
                course_id=item.courseId,
                section_id=item.sectionId,
                times_days=item.timesDays,
            )
        )
    schedule.detailed_courses = detailed_courses

    activities_payload = body.activities or []
    schedule.activities = [
        ScheduleActivityORM(
            schedule_id=schedule.id,
            description=activity.description,
            times_days=activity.timesDays,
        )
        for activity in activities_payload
    ]

    if favorite_flag:
        await session.execute(
            update(ScheduleORM)
            .where(ScheduleORM.user_id == userId, ScheduleORM.id != schedule.id)
            .values(is_starred=False)
        )

    await session.commit()
    await session.refresh(schedule)
    return _map_schedule(schedule)


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

    if body.difficultyScore is not None:
        schedule.difficulty_score = body.difficultyScore

    if body.items is not None:
        schedule.detailed_courses.clear()
        for item in body.items:
            await _get_or_create_course(item.courseId, session)
            schedule.detailed_courses.append(
                ScheduleCourseORM(
                    schedule_id=schedule.id,
                    course_id=item.courseId,
                    section_id=item.sectionId,
                    times_days=item.timesDays,
                )
            )

    if body.activities is not None:
        schedule.activities.clear()
        schedule.activities.extend(
            ScheduleActivityORM(
                schedule_id=schedule.id,
                description=activity.description,
                times_days=activity.timesDays,
            )
            for activity in body.activities
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
