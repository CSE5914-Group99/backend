from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Declarative base for ORM models."""


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("username", name="uq_users_username"),
        UniqueConstraint("email", name="uq_users_email"),
        UniqueConstraint("google_uid", name="uq_users_google_uid"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(50), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    # Keep hashed_password nullable for OAuth-created users who may not have one
    hashed_password: Mapped[str | None] = mapped_column(String(255), nullable=True)
    google_uid: Mapped[str | None] = mapped_column(String(255), nullable=True)
    first_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    last_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    date_of_birth: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=True)

    schedules: Mapped[list[Schedule]] = relationship(
        back_populates="user", cascade="all, delete-orphan", lazy="selectin"
    )


class Schedule(Base):
    __tablename__ = "schedules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False, default="Untitled")
    is_starred: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Schedule scoring fields
    total_credit_hours: Mapped[int | None] = mapped_column(Integer, nullable=True)
    num_classes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    adjusted_difficulty: Mapped[int | None] = mapped_column(Integer, nullable=True)
    adjusted_assessment_intensity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    adjusted_project_intensity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    time_load: Mapped[float | None] = mapped_column(Float, nullable=True)
    adjusted_rigor: Mapped[int | None] = mapped_column(Integer, nullable=True)
    constraints: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)

    user: Mapped[User] = relationship(back_populates="schedules")
    activities: Mapped[list[ScheduleActivity]] = relationship(
        back_populates="schedule", cascade="all, delete-orphan", lazy="selectin"
    )
    # Timing/section info for courses in this schedule
    detailed_courses: Mapped[list[ScheduleCourse]] = relationship(
        back_populates="schedule", cascade="all, delete-orphan", lazy="selectin"
    )


class Course(Base):
    __tablename__ = "courses"
    __table_args__ = (
        UniqueConstraint("course_id", "teacher_name", name="uq_course_teacher"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    course_id: Mapped[str] = mapped_column(String(50), nullable=False)
    teacher_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    course_rating: Mapped[dict] = mapped_column(JSON, nullable=False)


class ScheduleActivity(Base):
    __tablename__ = "schedule_activities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    schedule_id: Mapped[int] = mapped_column(ForeignKey("schedules.id", ondelete="CASCADE"), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    times_days: Mapped[str | None] = mapped_column(String(255), nullable=True)

    schedule: Mapped[Schedule] = relationship(back_populates="activities")


class ScheduleCourseLink(Base):
    """Pure junction table linking schedules to courses (composite primary key)"""
    __tablename__ = "schedule_course_links"
    __table_args__ = (
        ForeignKeyConstraint(
            ["course_id", "teacher_name"],
            ["courses.course_id", "courses.teacher_name"],
            ondelete="CASCADE"
        ),
    )

    schedule_id: Mapped[int] = mapped_column(ForeignKey("schedules.id", ondelete="CASCADE"), primary_key=True)
    course_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    teacher_name: Mapped[str] = mapped_column(String(255), primary_key=True, default="unknown")


class ScheduleCourse(Base):
    """Stores section/timing information for courses in a schedule"""
    __tablename__ = "schedule_courses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    schedule_id: Mapped[int] = mapped_column(ForeignKey("schedules.id", ondelete="CASCADE"), nullable=False)
    course_id: Mapped[str] = mapped_column(String(50), nullable=False)
    teacher_name: Mapped[str] = mapped_column(String(255), nullable=False, default="unknown")
    section_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    times_days: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Relationship back to parent schedule for automatic schedule_id assignment
    schedule: Mapped[Schedule] = relationship(back_populates="detailed_courses")
