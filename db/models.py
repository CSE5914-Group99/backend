from __future__ import annotations

from datetime import date, datetime
from typing import Any

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
        UniqueConstraint("email", name="uq_users_email"),
    )

    google_uid: Mapped[str] = mapped_column(String(255), primary_key=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    preferences: Mapped[str] = mapped_column(Text, nullable=False, default="")
    
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
    user_id: Mapped[str] = mapped_column(ForeignKey("users.google_uid", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False, default="Untitled")
    is_starred: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    campus: Mapped[str | None] = mapped_column(String(100), nullable=True)
    semester: Mapped[str | None] = mapped_column(String(100), nullable=True)
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

    @property
    def courses(self) -> list[ScheduleCourse]:
        return self.detailed_courses

    @property
    def events(self) -> list[ScheduleActivity]:
        return self.activities

    @property
    def favorite(self) -> bool:
        return self.is_starred

    @property
    def difficultyScore(self) -> float | None:
        # Map adjusted_difficulty to difficultyScore if needed, or just return None
        return float(self.adjusted_difficulty) if self.adjusted_difficulty is not None else None

    @property
    def weeklyHours(self) -> float | None:
        return self.time_load

    @property
    def creditHours(self) -> float | None:
        return float(self.total_credit_hours) if self.total_credit_hours is not None else None

    @property
    def createdAt(self) -> datetime:
        return self.created_at

    @property
    def updatedAt(self) -> datetime | None:
        # If we don't have updated_at, use created_at
        return self.created_at



class ScheduleActivity(Base):
    __tablename__ = "schedule_activities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    schedule_id: Mapped[int] = mapped_column(ForeignKey("schedules.id", ondelete="CASCADE"), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False, default="Untitled")
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    times_days: Mapped[str | None] = mapped_column(String(255), nullable=True)
    campus: Mapped[str | None] = mapped_column(String(100), nullable=True)
    semester: Mapped[str | None] = mapped_column(String(100), nullable=True)

    schedule: Mapped[Schedule] = relationship(back_populates="activities")

    @property
    def startTime(self) -> str | None:
        if not self.times_days:
            return None
        import re
        match = re.search(r'(\d{1,2}:\d{2})-(\d{1,2}:\d{2})', self.times_days)
        return match.group(1) if match else None

    @property
    def endTime(self) -> str | None:
        if not self.times_days:
            return None
        import re
        match = re.search(r'(\d{1,2}:\d{2})-(\d{1,2}:\d{2})', self.times_days)
        return match.group(2) if match else None

    @property
    def repeatDays(self) -> list[str]:
        if not self.times_days:
            return []
        days = []
        for day in ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']:
            if day in self.times_days:
                days.append(day)
        return days


class ScheduleCourse(Base):
    """Stores section/timing information for courses in a schedule"""
    __tablename__ = "schedule_courses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    schedule_id: Mapped[int] = mapped_column(ForeignKey("schedules.id", ondelete="CASCADE"), nullable=False)
    course_id: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    teacher_name: Mapped[str] = mapped_column(String(255), nullable=False, default="unknown")
    section_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    times_days: Mapped[str | None] = mapped_column(String(255), nullable=True)
    campus: Mapped[str | None] = mapped_column(String(100), nullable=True)
    semester: Mapped[str | None] = mapped_column(String(100), nullable=True)
    type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    difficulty_rating: Mapped[float | None] = mapped_column(Float, nullable=True)
    mode: Mapped[str | None] = mapped_column(String(50), nullable=True)
    status: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Relationship back to parent schedule for automatic schedule_id assignment
    schedule: Mapped[Schedule] = relationship(back_populates="detailed_courses")

    @property
    def courseId(self) -> str:
        return self.course_id

    @property
    def instructor(self) -> str:
        return self.teacher_name

    @property
    def startTime(self) -> str | None:
        if not self.times_days:
            return None
        import re
        match = re.search(r'(\d{1,2}:\d{2})-(\d{1,2}:\d{2})', self.times_days)
        return match.group(1) if match else None

    @property
    def endTime(self) -> str | None:
        if not self.times_days:
            return None
        import re
        match = re.search(r'(\d{1,2}:\d{2})-(\d{1,2}:\d{2})', self.times_days)
        return match.group(2) if match else None

    @property
    def repeatDays(self) -> list[str]:
        if not self.times_days:
            return []
        days = []
        # Simple check for day names
        for day in ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']:
            if day in self.times_days:
                days.append(day)
        return days

    @property
    def difficultyRating(self) -> float | None:
        return self.difficulty_rating

    @property
    def session(self) -> int | None:
        return int(self.section_id) if self.section_id and self.section_id.isdigit() else None

