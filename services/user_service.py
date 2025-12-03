from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db import User as UserORM
from schemas import UserCreate, UserUpdate

async def get_user_by_google_uid(google_uid: str, session: AsyncSession) -> UserORM | None:
    return await session.scalar(select(UserORM).where(UserORM.google_uid == google_uid))

async def get_user_by_email(email: str, session: AsyncSession) -> UserORM | None:
    return await session.scalar(select(UserORM).where(UserORM.email == email))

async def create_user(user: UserCreate, session: AsyncSession) -> UserORM:
    # If this is an OAuth signup (google_uid provided), check by google_uid first
    if user.google_uid:
        existing_by_google = await get_user_by_google_uid(user.google_uid, session)
        if existing_by_google:
            return existing_by_google

    existing = await get_user_by_email(user.email, session)
    if existing:
        raise HTTPException(status_code=409, detail="User already exists")

    db_user = UserORM(
        email=user.email,
        google_uid=user.google_uid,
        first_name=user.first_name,
        last_name=user.last_name,
        date_of_birth=user.date_of_birth,
        preferences=user.preferences or "",
    )
    session.add(db_user)
    await session.flush()
    await session.commit()
    await session.refresh(db_user)
    return db_user

async def update_user(google_uid: str, payload: UserUpdate, session: AsyncSession) -> UserORM:
    user = await get_user_by_google_uid(google_uid, session)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if payload.email and payload.email != user.email:
        exists = await get_user_by_email(payload.email, session)
        if exists:
            raise HTTPException(status_code=409, detail="Email already in use")
        user.email = payload.email

    if payload.google_uid and payload.google_uid != user.google_uid:
        exists = await get_user_by_google_uid(payload.google_uid, session)
        if exists:
            raise HTTPException(status_code=409, detail="Google UID already in use")
        user.google_uid = payload.google_uid

    if payload.first_name is not None:
        user.first_name = payload.first_name

    if payload.last_name is not None:
        user.last_name = payload.last_name

    if payload.date_of_birth is not None:
        user.date_of_birth = payload.date_of_birth

    if payload.preferences is not None:
        user.preferences = payload.preferences

    await session.commit()
    await session.refresh(user)
    return user

async def delete_user(google_uid: str, session: AsyncSession) -> None:
    user = await get_user_by_google_uid(google_uid, session)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    await session.delete(user)
    await session.commit()
