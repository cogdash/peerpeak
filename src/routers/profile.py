"""Profile routes."""

from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from core.database import SessionLocal
from core.ids import generate_id
from core.auth import (
    pwd_context,
    SESSION_EXPIRY_DAYS,
    hash_password,
    verify_password,
    create_session,
    get_current_user,
    require_auth,
    get_db,
)
from core.dependencies import templates
from models import User, Session as SessionModel

router = APIRouter()


@router.get("/profile", response_class=HTMLResponse)
def profile_page(
    request: Request,
    user: User = Depends(require_auth),
    db: Session = Depends(get_db),
    show_all: bool = False,
):
    # Get user's badges
    from models import UserBadge, Badge

    user_badges = db.query(UserBadge).filter(UserBadge.user_id == user.id).all()
    badge_ids = [ub.badge_id for ub in user_badges]
    badges = db.query(Badge).filter(Badge.id.in_(badge_ids)).all() if badge_ids else []

    # Get user's stories
    from models import Story

    stories = (
        db.query(Story)
        .filter(Story.author_id == user.id)
        .order_by(Story.created_at.desc())
        .all()
    )

    # Get user's sessions
    from models import Session as SessionModel

    query = db.query(SessionModel).filter(SessionModel.user_id == user.id)
    if not show_all:
        query = query.filter(SessionModel.terminated == False)
    sessions = query.order_by(SessionModel.start_time.desc()).all()

    # Convert sessions to dict for JSON serialization
    sessions_data = []
    for session in sessions:
        sessions_data.append(
            {
                "id": session.id,
                "useragent": session.useragent,
                "ip": session.ip,
                "location": session.location,
                "start_time": session.start_time.isoformat()
                if session.start_time
                else None,
                "end_time": session.end_time.isoformat() if session.end_time else None,
                "terminated": session.terminated,
            }
        )

    # Convert user to dict for JSON serialization
    user_data = {
        "id": user.id,
        "name": user.name,
        "display_name": user.display_name,
        "bio": user.bio,
        "username_change_count": user.username_change_count,
        "last_username_change": user.last_username_change.isoformat()
        if user.last_username_change
        else None,
    }

    # Convert badges to dict
    badges_data = []
    for badge in badges:
        badges_data.append(
            {
                "id": badge.id,
                "name": badge.name,
                "description": badge.description,
                "type": badge.type.value if badge.type else "custom",
            }
        )

    # Convert stories to dict
    stories_data = []
    for story in stories:
        stories_data.append(
            {
                "id": story.id,
                "title": story.title,
                "content": story.content,
                "created_at": story.created_at.isoformat()
                if story.created_at
                else None,
            }
        )

    context = {
        "request": request,
        "user": user_data,
        "badges": badges_data,
        "stories": stories_data,
        "sessions": sessions_data,
        "view": "profile",
        "show_all": show_all,
    }
    return templates.TemplateResponse(request, "profile.html", context)


@router.get("/profile/account", response_class=HTMLResponse)
def account_page(
    request: Request,
    user: User = Depends(require_auth),
    db: Session = Depends(get_db),
    show_all: bool = False,
):
    # Get user's sessions
    query = db.query(SessionModel).filter(SessionModel.user_id == user.id)
    if not show_all:
        query = query.filter(SessionModel.terminated == False)
    sessions = query.order_by(SessionModel.start_time.desc()).all()

    # Convert sessions to dict for JSON serialization
    sessions_data = []
    for session in sessions:
        sessions_data.append(
            {
                "id": session.id,
                "useragent": session.useragent,
                "ip": session.ip,
                "location": session.location,
                "start_time": session.start_time.isoformat()
                if session.start_time
                else None,
                "end_time": session.end_time.isoformat() if session.end_time else None,
                "terminated": session.terminated,
            }
        )

    # Convert user to dict for JSON serialization
    user_data = {
        "id": user.id,
        "name": user.name,
        "display_name": user.display_name,
        "bio": user.bio,
        "username_change_count": user.username_change_count,
        "last_username_change": user.last_username_change.isoformat()
        if user.last_username_change
        else None,
    }

    context = {
        "request": request,
        "user": user_data,
        "sessions": sessions_data,
        "badges": [],  # Empty for account view
        "stories": [],  # Empty for account view
        "view": "account",
        "show_all": show_all,
    }
    return templates.TemplateResponse(request, "profile.html", context)


@router.get("/profile/sessions")
def get_sessions(
    request: Request,
    user: User = Depends(require_auth),
    db: Session = Depends(get_db),
    show_all: bool = False,
):
    # Get user's sessions
    query = db.query(SessionModel).filter(SessionModel.user_id == user.id)
    if not show_all:
        query = query.filter(SessionModel.terminated == False)
    sessions = query.order_by(SessionModel.start_time.desc()).all()

    # Convert sessions to dict for JSON serialization
    sessions_data = []
    for session in sessions:
        sessions_data.append(
            {
                "id": session.id,
                "useragent": session.useragent,
                "ip": session.ip,
                "location": session.location,
                "start_time": session.start_time.isoformat()
                if session.start_time
                else None,
                "end_time": session.end_time.isoformat() if session.end_time else None,
                "terminated": session.terminated,
            }
        )

    return {"sessions": sessions_data}


@router.post("/profile/terminate-session")
def terminate_session(
    request: Request,
    session_id: str = Form(...),
    user: User = Depends(require_auth),
    db: Session = Depends(get_db),
):
    session = (
        db.query(SessionModel)
        .filter(SessionModel.id == session_id, SessionModel.user_id == user.id)
        .first()
    )

    if session and not session.terminated:
        session.terminated = True
        session.end_time = datetime.now(timezone.utc)
        db.commit()

    return RedirectResponse(url="/profile", status_code=status.HTTP_302_FOUND)


@router.post("/profile/delete-account")
def delete_account(
    request: Request,
    password: str = Form(...),
    user: User = Depends(require_auth),
    db: Session = Depends(get_db),
):
    if not verify_password(password, user.password):
        return RedirectResponse(
            url="/profile?error=invalid_password", status_code=status.HTTP_302_FOUND
        )

    # Terminate all sessions
    sessions = db.query(SessionModel).filter(SessionModel.user_id == user.id).all()
    for session in sessions:
        session.terminated = True
        session.end_time = datetime.now(timezone.utc)

    # Delete user (cascades to related records)
    db.delete(user)
    db.commit()

    response = RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    response.delete_cookie("session_id")
    return response


@router.post("/profile/update")
def update_profile(
    request: Request,
    display_name: str = Form(""),
    bio: str = Form(""),
    new_username: str = Form(""),
    user: User = Depends(require_auth),
    db: Session = Depends(get_db),
):
    # Handle username change if provided
    if new_username and new_username != user.name:
        # Check if username is already taken
        existing_user = db.query(User).filter(User.name == new_username).first()
        if existing_user and existing_user.id != user.id:
            return RedirectResponse(
                url="/profile?username_error=Username already taken",
                status_code=status.HTTP_302_FOUND,
            )

        # Check username change limit (2 times per week)
        now = datetime.now(timezone.utc)
        if user.last_username_change:
            week_ago = now - timedelta(weeks=1)
            if user.last_username_change > week_ago and user.username_change_count >= 2:
                return RedirectResponse(
                    url="/profile?username_error=You can only change your username 2 times per week",
                    status_code=status.HTTP_302_FOUND,
                )
            elif user.last_username_change <= week_ago:
                # Reset count if last change was more than a week ago
                user.username_change_count = 0

        user.name = new_username
        user.username_change_count += 1
        user.last_username_change = now

    if display_name:
        user.display_name = display_name
    if bio is not None:
        user.bio = bio if bio else None
    db.commit()
    return RedirectResponse(
        url="/profile?success=Profile updated successfully",
        status_code=status.HTTP_302_FOUND,
    )


@router.post("/profile/update-username")
def update_username(
    request: Request,
    new_username: str = Form(...),
    user: User = Depends(require_auth),
    db: Session = Depends(get_db),
):
    # Check if username is already taken
    existing_user = db.query(User).filter(User.name == new_username).first()
    if existing_user and existing_user.id != user.id:
        return RedirectResponse(
            url="/profile?username_error=Username already taken",
            status_code=status.HTTP_302_FOUND,
        )

    # Check username change limit (2 times per week)
    now = datetime.now(timezone.utc)
    if user.last_username_change:
        week_ago = now - timedelta(weeks=1)
        if user.last_username_change > week_ago and user.username_change_count >= 2:
            return RedirectResponse(
                url="/profile?username_error=You can only change your username 2 times per week",
                status_code=status.HTTP_302_FOUND,
            )
        elif user.last_username_change <= week_ago:
            # Reset count if last change was more than a week ago
            user.username_change_count = 0

    user.name = new_username
    user.username_change_count += 1
    user.last_username_change = now
    db.commit()

    return RedirectResponse(
        url="/profile?username_success=Username changed successfully",
        status_code=status.HTTP_302_FOUND,
    )
