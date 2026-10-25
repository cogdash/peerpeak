"""Authentication helpers: password hashing, sessions and FastAPI dependencies.

The application keeps users logged in with an opaque session token stored in an
``AUTH_TOKEN`` cookie. The token is the primary key of a row in the ``sessions``
table, so revoking a session is as simple as deleting that row.
"""

import uuid
from datetime import datetime, timezone

from fastapi import Cookie, Depends, HTTPException, Request, Response, status
from pwdlib import PasswordHash
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Session, User
from db.models.session import SESSION_TTL
from db.session import get_session

# Cookie name used to carry the session token between the browser and the API.
AUTH_COOKIE_NAME = "AUTH_TOKEN"

# Argon2 is the default recommended algorithm for pwdlib.
_password_hash = PasswordHash.recommended()


def hash_password(password: str) -> str:
    """Return a salted hash suitable for storing in ``users.password``."""
    return _password_hash.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """Check a plaintext password against a stored hash."""
    return _password_hash.verify(password, password_hash)


def set_auth_cookie(response: Response, token: uuid.UUID) -> None:
    """Attach the session token to the response as an HttpOnly cookie.

    ``httponly`` keeps the token out of reach of JavaScript (mitigating XSS),
    while ``samesite="lax"`` still allows the cookie on top-level navigations.
    """
    response.set_cookie(
        key=AUTH_COOKIE_NAME,
        value=str(token),
        httponly=True,
        samesite="lax",
        secure=False,  # set to True once the app is served over HTTPS
        max_age=int(SESSION_TTL.total_seconds()),
        path="/",
    )


def clear_auth_cookie(response: Response) -> None:
    """Remove the session cookie from the browser."""
    response.delete_cookie(key=AUTH_COOKIE_NAME, path="/")


async def create_session(
    session: AsyncSession,
    user: User,
    request: Request,
) -> Session:
    """Create and persist a new session row for ``user``.

    The caller is responsible for committing the surrounding transaction.
    """
    user_agent = request.headers.get("user-agent")
    if user_agent is not None:
        user_agent = user_agent[:512]

    client_host = request.client.host if request.client else None
    if client_host is not None:
        client_host = client_host[:45]

    db_session = Session(
        user_id=user.id,
        user_agent=user_agent,
        ip_address=client_host,
    )
    session.add(db_session)
    await session.flush()
    return db_session


async def get_current_user(
    auth_token: str | None = Cookie(default=None, alias=AUTH_COOKIE_NAME),
    session: AsyncSession = Depends(get_session),
) -> User:
    """Resolve the authenticated user from the ``AUTH_TOKEN`` cookie.

    Raises ``401`` when the cookie is missing, malformed, unknown or expired.
    """
    if not auth_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )

    try:
        token = uuid.UUID(auth_token)
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid session token",
        )

    result = await session.execute(
        select(Session).where(Session.token == token)
    )
    db_session = result.scalar_one_or_none()

    if db_session is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session not found",
        )

    if db_session.expires_at <= datetime.now(tz=timezone.utc):
        # Expired sessions are useless; drop them so the table stays tidy.
        await session.delete(db_session)
        await session.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired",
        )

    user = await session.get(User, db_session.user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

    return user


async def get_optional_user(
    auth_token: str | None = Cookie(default=None, alias=AUTH_COOKIE_NAME),
    session: AsyncSession = Depends(get_session),
) -> User | None:
    """Resolve the current user, or return ``None`` for guests.

    Useful for public endpoints that render a different response to the
    authenticated owner of the session (for example, whether the viewer
    already follows the requested profile).
    """
    if not auth_token:
        return None

    try:
        return await get_current_user(auth_token=auth_token, session=session)
    except HTTPException:
        return None

