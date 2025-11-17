"""CRUD operations for the courses table."""

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Course


async def create_course(
    session: AsyncSession,
    course_id: str,
    teacher_name: str,
    course_rating: dict
) -> Course:
    """
    Create a new course rating.

    Args:
        session: Database session
        course_id: Course identifier (e.g., "CSE2331")
        teacher_name: Teacher's name
        course_rating: JSON object containing ClassScore data

    Returns:
        Created Course object

    Raises:
        IntegrityError: If course with this course_id + teacher_name already exists
    """
    course = Course(
        course_id=course_id,
        teacher_name=teacher_name,
        course_rating=course_rating
    )
    session.add(course)
    await session.commit()
    await session.refresh(course)
    return course


async def get_course(
    session: AsyncSession,
    course_id: str,
    teacher_name: str
) -> Course | None:
    """
    Get a course by composite key (course_id, teacher_name).

    Args:
        session: Database session
        course_id: Course identifier
        teacher_name: Teacher's name

    Returns:
        Course object if found, None otherwise
    """
    stmt = select(Course).where(
        Course.course_id == course_id,
        Course.teacher_name == teacher_name
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_all_courses(session: AsyncSession) -> list[Course]:
    """
    Get all courses.

    Args:
        session: Database session

    Returns:
        List of all Course objects
    """
    stmt = select(Course)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_courses_by_course_id(
    session: AsyncSession,
    course_id: str
) -> list[Course]:
    """
    Get all ratings for a specific course (all teachers).

    Args:
        session: Database session
        course_id: Course identifier

    Returns:
        List of Course objects for this course_id with different teachers
    """
    stmt = select(Course).where(Course.course_id == course_id)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_courses_by_teacher(
    session: AsyncSession,
    teacher_name: str
) -> list[Course]:
    """
    Get all courses taught by a specific teacher.

    Args:
        session: Database session
        teacher_name: Teacher's name

    Returns:
        List of Course objects taught by this teacher
    """
    stmt = select(Course).where(Course.teacher_name == teacher_name)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def update_course(
    session: AsyncSession,
    course_id: str,
    teacher_name: str,
    course_rating: dict
) -> Course | None:
    """
    Update a course's rating.

    Args:
        session: Database session
        course_id: Course identifier
        teacher_name: Teacher's name
        course_rating: New JSON object containing ClassScore data

    Returns:
        Updated Course object if found, None otherwise
    """
    course = await get_course(session, course_id, teacher_name)
    if course:
        course.course_rating = course_rating
        await session.commit()
        await session.refresh(course)
    return course


async def upsert_course(
    session: AsyncSession,
    course_id: str,
    teacher_name: str,
    course_rating: dict
) -> Course:
    """
    Create or update a course rating (upsert).

    Args:
        session: Database session
        course_id: Course identifier
        teacher_name: Teacher's name
        course_rating: JSON object containing ClassScore data

    Returns:
        Course object (either created or updated)
    """
    course = await get_course(session, course_id, teacher_name)
    if course:
        course.course_rating = course_rating
        await session.commit()
        await session.refresh(course)
    else:
        course = await create_course(session, course_id, teacher_name, course_rating)
    return course


async def delete_course(
    session: AsyncSession,
    course_id: str,
    teacher_name: str
) -> bool:
    """
    Delete a course rating.

    Args:
        session: Database session
        course_id: Course identifier
        teacher_name: Teacher's name

    Returns:
        True if course was deleted, False if not found
    """
    stmt = delete(Course).where(
        Course.course_id == course_id,
        Course.teacher_name == teacher_name
    )
    result = await session.execute(stmt)
    await session.commit()
    return result.rowcount > 0


async def delete_all_courses_for_course_id(
    session: AsyncSession,
    course_id: str
) -> int:
    """
    Delete all ratings for a specific course (all teachers).

    Args:
        session: Database session
        course_id: Course identifier

    Returns:
        Number of courses deleted
    """
    stmt = delete(Course).where(Course.course_id == course_id)
    result = await session.execute(stmt)
    await session.commit()
    return result.rowcount
