"""CRUD operations for the schedule_course_links table."""

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import ScheduleCourseLink


async def create_schedule_course_link(
    session: AsyncSession,
    schedule_id: int,
    course_id: str,
    teacher_name: str = "unknown"
) -> ScheduleCourseLink:
    """
    Create a link between a schedule and a course.

    Args:
        session: Database session
        schedule_id: Schedule identifier
        course_id: Course identifier
        teacher_name: Teacher's name (default: "unknown")

    Returns:
        Created ScheduleCourseLink object

    Raises:
        IntegrityError: If link already exists or foreign keys are invalid
    """
    link = ScheduleCourseLink(
        schedule_id=schedule_id,
        course_id=course_id,
        teacher_name=teacher_name
    )
    session.add(link)
    await session.commit()
    await session.refresh(link)
    return link


async def get_schedule_course_link(
    session: AsyncSession,
    schedule_id: int,
    course_id: str,
    teacher_name: str
) -> ScheduleCourseLink | None:
    """
    Get a specific schedule-course link.

    Args:
        session: Database session
        schedule_id: Schedule identifier
        course_id: Course identifier
        teacher_name: Teacher's name

    Returns:
        ScheduleCourseLink object if found, None otherwise
    """
    stmt = select(ScheduleCourseLink).where(
        ScheduleCourseLink.schedule_id == schedule_id,
        ScheduleCourseLink.course_id == course_id,
        ScheduleCourseLink.teacher_name == teacher_name
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_all_schedule_course_links(session: AsyncSession) -> list[ScheduleCourseLink]:
    """
    Get all schedule-course links.

    Args:
        session: Database session

    Returns:
        List of all ScheduleCourseLink objects
    """
    stmt = select(ScheduleCourseLink)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_courses_for_schedule(
    session: AsyncSession,
    schedule_id: int
) -> list[ScheduleCourseLink]:
    """
    Get all courses linked to a specific schedule.

    Args:
        session: Database session
        schedule_id: Schedule identifier

    Returns:
        List of ScheduleCourseLink objects for this schedule
    """
    stmt = select(ScheduleCourseLink).where(
        ScheduleCourseLink.schedule_id == schedule_id
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_schedules_with_course(
    session: AsyncSession,
    course_id: str,
    teacher_name: str
) -> list[ScheduleCourseLink]:
    """
    Get all schedules that include a specific course.

    Args:
        session: Database session
        course_id: Course identifier
        teacher_name: Teacher's name

    Returns:
        List of ScheduleCourseLink objects for this course
    """
    stmt = select(ScheduleCourseLink).where(
        ScheduleCourseLink.course_id == course_id,
        ScheduleCourseLink.teacher_name == teacher_name
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def add_courses_to_schedule(
    session: AsyncSession,
    schedule_id: int,
    courses: list[tuple[str, str]]
) -> list[ScheduleCourseLink]:
    """
    Add multiple courses to a schedule.

    Args:
        session: Database session
        schedule_id: Schedule identifier
        courses: List of (course_id, teacher_name) tuples

    Returns:
        List of created ScheduleCourseLink objects
    """
    links = []
    for course_id, teacher_name in courses:
        link = ScheduleCourseLink(
            schedule_id=schedule_id,
            course_id=course_id,
            teacher_name=teacher_name
        )
        session.add(link)
        links.append(link)

    await session.commit()

    # Refresh all links
    for link in links:
        await session.refresh(link)

    return links


async def delete_schedule_course_link(
    session: AsyncSession,
    schedule_id: int,
    course_id: str,
    teacher_name: str
) -> bool:
    """
    Delete a specific schedule-course link.

    Args:
        session: Database session
        schedule_id: Schedule identifier
        course_id: Course identifier
        teacher_name: Teacher's name

    Returns:
        True if link was deleted, False if not found
    """
    stmt = delete(ScheduleCourseLink).where(
        ScheduleCourseLink.schedule_id == schedule_id,
        ScheduleCourseLink.course_id == course_id,
        ScheduleCourseLink.teacher_name == teacher_name
    )
    result = await session.execute(stmt)
    await session.commit()
    return result.rowcount > 0


async def delete_all_courses_from_schedule(
    session: AsyncSession,
    schedule_id: int
) -> int:
    """
    Remove all courses from a schedule.

    Args:
        session: Database session
        schedule_id: Schedule identifier

    Returns:
        Number of links deleted
    """
    stmt = delete(ScheduleCourseLink).where(
        ScheduleCourseLink.schedule_id == schedule_id
    )
    result = await session.execute(stmt)
    await session.commit()
    return result.rowcount


async def delete_course_from_all_schedules(
    session: AsyncSession,
    course_id: str,
    teacher_name: str
) -> int:
    """
    Remove a specific course from all schedules.

    Args:
        session: Database session
        course_id: Course identifier
        teacher_name: Teacher's name

    Returns:
        Number of links deleted
    """
    stmt = delete(ScheduleCourseLink).where(
        ScheduleCourseLink.course_id == course_id,
        ScheduleCourseLink.teacher_name == teacher_name
    )
    result = await session.execute(stmt)
    await session.commit()
    return result.rowcount
