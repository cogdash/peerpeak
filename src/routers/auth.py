"""Authentication routes."""

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


@router.get("/", response_class=HTMLResponse)
def read_root(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if user:
        return RedirectResponse(url="/feed", status_code=status.HTTP_302_FOUND)
    return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if user:
        return RedirectResponse(url="/feed", status_code=status.HTTP_302_FOUND)
    context = {"request": request, "error": None}
    return templates.TemplateResponse(request, "login.html", context)


@router.post("/login", response_class=HTMLResponse)
def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.name == username).first()

    if not user or not verify_password(password, user.password):
        context = {"request": request, "error": "Invalid username or password"}
        return templates.TemplateResponse(
            request, "login.html", context, status_code=401
        )

    session = create_session(db, user.id, request)
    response = RedirectResponse(url="/feed", status_code=status.HTTP_302_FOUND)
    response.set_cookie(
        key="session_id",
        value=session.id,
        httponly=True,
        secure=False,  # Set to True in production with HTTPS
        samesite="lax",
        max_age=SESSION_EXPIRY_DAYS * 24 * 60 * 60,
    )
    return response


@router.get("/signup", response_class=HTMLResponse)
def signup_page(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if user:
        return RedirectResponse(url="/feed", status_code=status.HTTP_302_FOUND)
    context = {"request": request, "error": None}
    return templates.TemplateResponse(request, "signup.html", context)


@router.post("/signup", response_class=HTMLResponse)
def signup(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    display_name: str = Form(""),
    db: Session = Depends(get_db),
):
    # Check if username exists
    existing_user = db.query(User).filter(User.name == username).first()
    if existing_user:
        context = {"request": request, "error": "Username already taken"}
        return templates.TemplateResponse(
            request, "signup.html", context, status_code=400
        )

    # Create user
    user = User(
        id=generate_id(),
        name=username,
        password=hash_password(password),
        display_name=display_name if display_name else None,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    # Create session
    session = create_session(db, user.id, request)
    response = RedirectResponse(url="/feed", status_code=status.HTTP_302_FOUND)
    response.set_cookie(
        key="session_id",
        value=session.id,
        httponly=True,
        secure=False,
        samesite="lax",
        max_age=SESSION_EXPIRY_DAYS * 24 * 60 * 60,
    )
    return response


@router.post("/logout")
def logout(request: Request, db: Session = Depends(get_db)):
    session_id = request.cookies.get("session_id")
    if session_id:
        session = db.query(SessionModel).filter(SessionModel.id == session_id).first()
        if session:
            session.terminated = True
            session.end_time = datetime.now(timezone.utc)
            db.commit()

    response = RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    response.delete_cookie("session_id")
    return response
