from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status, Response
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from db import User as UserORM, get_session
from schemas import User, UserCreate, UserUpdate
from security import hash_password

users_router = APIRouter(prefix="/users", tags=["users"])


@users_router.post(
    "/",
    response_model=User,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new user",
)
async def create_user(
    user: UserCreate, session: AsyncSession = Depends(get_session), response: Response = None
):
    # If this is an OAuth signup (google_uid provided), check by google_uid first
    if user.google_uid:
        existing_by_google = await session.scalar(select(UserORM).where(UserORM.google_uid == user.google_uid))
        if existing_by_google:
            # Prefer returning existing user (200) so frontend can continue smoothly
            if response is not None:
                response.status_code = status.HTTP_200_OK
            return User.model_validate(existing_by_google)

    existing = await session.scalar(
        select(UserORM).where(
            or_(UserORM.username == user.username, UserORM.email == user.email)
        )
    )
    if existing:
        raise HTTPException(status_code=409, detail="User already exists")

    db_user = UserORM(
        username=user.username,
        email=user.email,
        hashed_password=hash_password(user.password),
        google_uid=user.google_uid,
        first_name=user.first_name,
        last_name=user.last_name,
        date_of_birth=user.date_of_birth,
    )
    session.add(db_user)
    await session.flush()
    await session.commit()
    await session.refresh(db_user)
    return User.model_validate(db_user)


@users_router.get(
    "/{userId}",
    response_model=User,
    summary="Get a user by ID",
)
async def get_user(userId: int, session: AsyncSession = Depends(get_session)):
    user = await session.get(UserORM, userId)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return User.model_validate(user)


@users_router.get(
    "/google/{google_uid}",
    response_model=User,
    summary="Get a user by Google UID",
)
async def get_user_by_google(google_uid: str, session: AsyncSession = Depends(get_session)):
    """Fetch a user by their Google UID. Returns 200 with user or 404 if not found."""
    user = await session.scalar(select(UserORM).where(UserORM.google_uid == google_uid))
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return User.model_validate(user)


@users_router.put(
    "/{userId}",
    response_model=User,
    summary="Update a user by ID",
)
async def update_user(
    userId: int, payload: UserUpdate, session: AsyncSession = Depends(get_session)
):
    user = await session.get(UserORM, userId)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if payload.username and payload.username != user.username:
        exists = await session.scalar(
            select(UserORM).where(UserORM.username == payload.username)
        )
        if exists:
            raise HTTPException(status_code=409, detail="Username already in use")
        user.username = payload.username

    if payload.email and payload.email != user.email:
        exists = await session.scalar(select(UserORM).where(UserORM.email == payload.email))
        if exists:
            raise HTTPException(status_code=409, detail="Email already in use")
        user.email = payload.email

    if payload.password:
        user.hashed_password = hash_password(payload.password)

    if payload.first_name is not None:
        user.first_name = payload.first_name

    if payload.last_name is not None:
        user.last_name = payload.last_name

    if payload.date_of_birth is not None:
        user.date_of_birth = payload.date_of_birth

    await session.commit()
    await session.refresh(user)
    return User.model_validate(user)


@users_router.delete(
    "/{userId}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a user by ID",
)
async def delete_user(userId: int, session: AsyncSession = Depends(get_session)):
    user = await session.get(UserORM, userId)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    await session.delete(user)
    await session.commit()
