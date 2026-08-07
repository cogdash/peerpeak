"""Authentication utilities."""

from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from core.database import SessionLocal
from core.ids import generate_id
from models import User, Session as SessionModel


# Password hashing
from passlib.context import CryptContext

pwd_context = CryptContext(
    schemes=["bcrypt"], deprecated="auto", bcrypt__truncate_error=False
)

# Session expiry: 90 days
SESSION_EXPIRY_DAYS = 90


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def hash_password(password: str) -> str:
    # bcrypt has a 72-byte limit, truncate if necessary
    if len(password.encode("utf-8")) > 72:
        password = password[:72]
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    # bcrypt has a 72-byte limit, truncate if necessary
    if len(plain_password.encode("utf-8")) > 72:
        plain_password = plain_password[:72]
    return pwd_context.verify(plain_password, hashed_password)


def create_session(db: Session, user_id: str, request: Request) -> SessionModel:
    session = SessionModel(
        id=generate_id(),
        user_id=user_id,
        start_time=datetime.now(timezone.utc),
        ip=request.client.host if request.client else None,
        useragent=request.headers.get("user-agent"),
        location=None,  # Could be enhanced with geoip
        terminated=False,
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


def get_current_user(request: Request, db: Session = Depends(get_db)) -> Optional[User]:
    session_id = request.cookies.get("session_id")
    if not session_id:
        return None

    session = (
        db.query(SessionModel)
        .filter(SessionModel.id == session_id, SessionModel.terminated == False)
        .first()
    )

    if not session:
        return None

    # Check if session expired (90 days)
    # Handle both naive and timezone-aware datetimes for compatibility
    now = datetime.now(timezone.utc)
    start_time = session.start_time
    if start_time.tzinfo is None:
        # Naive datetime - assume UTC
        start_time = start_time.replace(tzinfo=timezone.utc)

    if start_time < now - timedelta(days=SESSION_EXPIRY_DAYS):
        session.terminated = True
        db.commit()
        return None

    user = db.query(User).filter(User.id == session.user_id).first()
    return user


def require_auth(request: Request, db: Session = Depends(get_db)) -> User:
    user = get_current_user(request, db)
    if not user:
        # Return 401 for API endpoints (tests expect this)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
    return user
