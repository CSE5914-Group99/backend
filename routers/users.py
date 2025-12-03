from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from db import get_session
from schemas import User, UserCreate, UserExists, UserUpdate
from services import user_service

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
        existing_by_google = await user_service.get_user_by_google_uid(user.google_uid, session)
        if existing_by_google:
            # Prefer returning existing user (200) so frontend can continue smoothly
            if response is not None:
                response.status_code = status.HTTP_200_OK
            return User.model_validate(existing_by_google)

    db_user = await user_service.create_user(user, session)
    return User.model_validate(db_user)


@users_router.get(
    "/{google_uid}",
    response_model=User,
    summary="Get a user by Google UID",
)
async def get_user(google_uid: str, session: AsyncSession = Depends(get_session)):
    user = await user_service.get_user_by_google_uid(google_uid, session)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return User.model_validate(user)


@users_router.get(
    "/google/{google_uid}",
    response_model=User,
    summary="Get a user by Google UID (Legacy)",
)
async def get_user_by_google(google_uid: str, session: AsyncSession = Depends(get_session)):
    """Fetch a user by their Google UID. Returns 200 with user or 404 if not found."""
    return await get_user(google_uid, session)


@users_router.get(
    "/google/{google_uid}/exists",
    response_model=UserExists,
    summary="Check if a user exists by Google UID",
)
async def user_exists_by_google(google_uid: str, session: AsyncSession = Depends(get_session)):
    """Return a flag indicating whether a user with the provided Google/Firebase UID exists."""
    user = await user_service.get_user_by_google_uid(google_uid, session)
    if not user:
        return UserExists(exists=False, user=None)
    return UserExists(exists=True, user=User.model_validate(user))


@users_router.put(
    "/{google_uid}",
    response_model=User,
    summary="Update a user by Google UID",
)
async def update_user(
    google_uid: str, payload: UserUpdate, session: AsyncSession = Depends(get_session)
):
    user = await user_service.update_user(google_uid, payload, session)
    return User.model_validate(user)


@users_router.delete(
    "/{google_uid}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a user by Google UID",
)
async def delete_user(google_uid: str, session: AsyncSession = Depends(get_session)):
    await user_service.delete_user(google_uid, session)

