"""Authentication endpoints: sign up, sign in and sign out."""

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth import (
    clear_auth_cookie,
    create_session,
    get_current_user,
    hash_password,
    set_auth_cookie,
    verify_password,
)
from db.models import User
from db.session import get_session

router = APIRouter(prefix="/api", tags=["auth"])


class SignUpRequest(BaseModel):
    username: str = Field(min_length=3, max_length=32)
    full_name: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=6, max_length=128)


class SignInRequest(BaseModel):
    username: str = Field(min_length=1, max_length=32)
    password: str = Field(min_length=1, max_length=128)


class UserResponse(BaseModel):
    id: str
    username: str
    full_name: str


def _user_response(user: User) -> UserResponse:
    return UserResponse(
        id=str(user.id),
        username=user.username,
        full_name=user.full_name,
    )


@router.post("/signup", status_code=status.HTTP_201_CREATED)
async def signup(
    payload: SignUpRequest,
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_session),
) -> UserResponse:
    """Register a new user and log them in immediately."""
    username = payload.username.strip()

    existing = await session.execute(
        select(User).where(User.username == username)
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Этот юзернейм уже занят",
        )

    user = User(
        username=username,
        full_name=payload.full_name.strip(),
        password=hash_password(payload.password),
    )
    session.add(user)
    await session.flush()

    db_session = await create_session(session, user, request)
    await session.commit()

    set_auth_cookie(response, db_session.token)
    return _user_response(user)


@router.post("/signin")
async def signin(
    payload: SignInRequest,
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_session),
) -> UserResponse:
    """Authenticate an existing user and issue a fresh session token."""
    username = payload.username.strip()

    result = await session.execute(
        select(User).where(User.username == username)
    )
    user = result.scalar_one_or_none()

    if user is None or not verify_password(payload.password, user.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверный юзернейм или пароль",
        )

    db_session = await create_session(session, user, request)
    await session.commit()

    set_auth_cookie(response, db_session.token)
    return _user_response(user)


@router.post("/signout")
async def signout(
    response: Response,
    user: User = Depends(get_current_user),
) -> dict[str, str]:
    """Clear the session cookie on the client."""
    clear_auth_cookie(response)
    return {"status": "ok"}


@router.get("/me")
async def me(user: User = Depends(get_current_user)) -> UserResponse:
    """Return the currently authenticated user."""
    return _user_response(user)
