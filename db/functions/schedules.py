"""CRUD operations for the schedules table."""

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Schedule


async def create_schedule(
    session: AsyncSession,
    user_id: int,
    name: str = "Untitled",
    is_starred: bool = False
) -> Schedule:
    """
    Create a new schedule.

    Args:
        session: Database session
        user_id: ID of the user who owns this schedule
        name: Schedule name (default: "Untitled")
        is_starred: Whether schedule is starred (default: False)

    Returns:
        Created Schedule object

    Raises:
        IntegrityError: If user_id doesn't exist
    """
    schedule = Schedule(
        user_id=user_id,
        name=name,
        is_starred=is_starred
    )
    session.add(schedule)
    await session.commit()
    await session.refresh(schedule)
    return schedule


async def get_schedule(
    session: AsyncSession,
    schedule_id: int
) -> Schedule | None:
    """
    Get a schedule by ID.

    Args:
        session: Database session
        schedule_id: Schedule identifier

    Returns:
        Schedule object if found, None otherwise
    """
    stmt = select(Schedule).where(Schedule.id == schedule_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_all_schedules(session: AsyncSession) -> list[Schedule]:
    """
    Get all schedules.

    Args:
        session: Database session

    Returns:
        List of all Schedule objects
    """
    stmt = select(Schedule)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_schedules_by_user(
    session: AsyncSession,
    user_id: int
) -> list[Schedule]:
    """
    Get all schedules for a specific user.

    Args:
        session: Database session
        user_id: User identifier

    Returns:
        List of Schedule objects for this user
    """
    stmt = select(Schedule).where(Schedule.user_id == user_id)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_starred_schedules(
    session: AsyncSession,
    user_id: int
) -> list[Schedule]:
    """
    Get all starred schedules for a specific user.

    Args:
        session: Database session
        user_id: User identifier

    Returns:
        List of starred Schedule objects for this user
    """
    stmt = select(Schedule).where(
        Schedule.user_id == user_id,
        Schedule.is_starred == True
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def update_schedule(
    session: AsyncSession,
    schedule_id: int,
    **kwargs
) -> Schedule | None:
    """
    Update a schedule's fields.

    Args:
        session: Database session
        schedule_id: Schedule identifier
        **kwargs: Fields to update (e.g., name, is_starred, summary, adjusted_difficulty, etc.)

    Returns:
        Updated Schedule object if found, None otherwise
    """
    schedule = await get_schedule(session, schedule_id)
    if schedule:
        for key, value in kwargs.items():
            if hasattr(schedule, key):
                setattr(schedule, key, value)
        await session.commit()
        await session.refresh(schedule)
    return schedule


async def update_schedule_scoring(
    session: AsyncSession,
    schedule_id: int,
    total_credit_hours: int,
    num_classes: int,
    summary: str,
    adjusted_difficulty: int,
    adjusted_assessment_intensity: int,
    adjusted_project_intensity: int,
    time_load: float,
    adjusted_rigor: int,
    constraints: str | None,
    confidence: float
) -> Schedule | None:
    """
    Update a schedule's scoring fields from ScheduleScore data.

    Args:
        session: Database session
        schedule_id: Schedule identifier
        total_credit_hours: Total credit hours
        num_classes: Number of classes
        summary: Overall summary
        adjusted_difficulty: Adjusted difficulty score
        adjusted_assessment_intensity: Adjusted assessment intensity
        adjusted_project_intensity: Adjusted project intensity
        time_load: Weekly time load
        adjusted_rigor: Adjusted rigor score
        constraints: User constraints
        confidence: Confidence score

    Returns:
        Updated Schedule object if found, None otherwise
    """
    return await update_schedule(
        session,
        schedule_id,
        total_credit_hours=total_credit_hours,
        num_classes=num_classes,
        summary=summary,
        adjusted_difficulty=adjusted_difficulty,
        adjusted_assessment_intensity=adjusted_assessment_intensity,
        adjusted_project_intensity=adjusted_project_intensity,
        time_load=time_load,
        adjusted_rigor=adjusted_rigor,
        constraints=constraints,
        confidence=confidence
    )


async def toggle_schedule_star(
    session: AsyncSession,
    schedule_id: int
) -> Schedule | None:
    """
    Toggle a schedule's starred status.

    Args:
        session: Database session
        schedule_id: Schedule identifier

    Returns:
        Updated Schedule object if found, None otherwise
    """
    schedule = await get_schedule(session, schedule_id)
    if schedule:
        schedule.is_starred = not schedule.is_starred
        await session.commit()
        await session.refresh(schedule)
    return schedule


async def delete_schedule(
    session: AsyncSession,
    schedule_id: int
) -> bool:
    """
    Delete a schedule.

    Args:
        session: Database session
        schedule_id: Schedule identifier

    Returns:
        True if schedule was deleted, False if not found
    """
    stmt = delete(Schedule).where(Schedule.id == schedule_id)
    result = await session.execute(stmt)
    await session.commit()
    return result.rowcount > 0


async def delete_all_schedules_for_user(
    session: AsyncSession,
    user_id: int
) -> int:
    """
    Delete all schedules for a specific user.

    Args:
        session: Database session
        user_id: User identifier

    Returns:
        Number of schedules deleted
    """
    stmt = delete(Schedule).where(Schedule.user_id == user_id)
    result = await session.execute(stmt)
    await session.commit()
    return result.rowcount
