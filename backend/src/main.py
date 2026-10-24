import os
import uuid

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pathlib import Path
from sqlalchemy import text, select, func
from sqlalchemy.ext.asyncio import AsyncSession

from auth import get_current_user
from db.models import Badge, User, UserBadge
from db.session import get_session
from routers.auth import router as auth_router
from routers.profile import router as profile_router

app = FastAPI()

BASE_DIR = Path(__file__).resolve().parent

STATIC_DIR = BASE_DIR / "static"
TEMPLATES_DIR = BASE_DIR / "templates"

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory=TEMPLATES_DIR)

app.include_router(auth_router)
app.include_router(profile_router)


async def _optional_user(request: Request, session: AsyncSession) -> User | None:
    """Return the authenticated user for a page request, or ``None``.

    Page routes cannot use the ``get_current_user`` dependency directly because
    they must redirect to ``/auth`` instead of returning a ``401``.
    """
    token = request.cookies.get("AUTH_TOKEN")
    if not token:
        return None
    try:
        return await get_current_user(auth_token=token, session=session)
    except Exception:
        return None


@app.get("/")
async def read_index(
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    # Unauthenticated visitors are sent straight to the auth page.
    user = await _optional_user(request, session)
    if user is None:
        return RedirectResponse(url="/auth", status_code=302)
    # Redirect logged-in users to their own profile page
    return RedirectResponse(url=f"/@{user.username}", status_code=302)


@app.get("/profile")
async def read_profile(
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    # Unauthenticated visitors are sent straight to the auth page.
    user = await _optional_user(request, session)
    if user is None:
        return RedirectResponse(url="/auth", status_code=302)
    # Redirect to the user's profile page
    return RedirectResponse(url=f"/@{user.username}", status_code=302)


@app.get("/@{username}")
async def read_user_profile(
    username: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    # Check if the user exists
    result = await session.execute(select(User).where(User.username == username))
    target_user = result.scalar_one_or_none()
    if target_user is None:
        raise HTTPException(status_code=404, detail="User not found")

    # Count received achievements by polarity for the link preview.
    counts_result = await session.execute(
        select(Badge.polarity, func.count())
        .join(UserBadge, UserBadge.badge_id == Badge.id)
        .where(
            UserBadge.user_id == target_user.id,
            UserBadge.received.is_(True),
        )
        .group_by(Badge.polarity)
    )
    counts = dict(counts_result.all())

    bio = (target_user.bio or "").strip()
    bio_excerpt = bio[:140] + ("…" if len(bio) > 140 else "")
    stats = f"🏆 {counts.get('positive', 0)} · 💀 {counts.get('negative', 0)}"
    og_description = f"{bio_excerpt} · {stats}" if bio_excerpt else stats

    # Unauthenticated visitors can view the profile
    user = await _optional_user(request, session)
    return templates.TemplateResponse(
        request,
        "profile.html",
        {
            "user": user,
            "profile_user": target_user,
            "og_description": og_description,
        },
    )


@app.get("/badge/{badge_id}")
async def read_badge_page(
    badge_id: uuid.UUID,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    # Badge pages are public, but an unknown badge id should not serve the page.
    badge = await session.get(Badge, badge_id)
    if badge is None:
        raise HTTPException(status_code=404, detail="Badge not found")

    user = await _optional_user(request, session)
    return templates.TemplateResponse(
        request,
        "badge.html",
        {
            "user": user,
            "badge": badge,
            "og_title": f"{badge.emoji or '🏅'} {badge.title}",
            "og_description": (
                "Анти-достижение в Peerpeak"
                if badge.polarity == "negative"
                else "Достижение в Peerpeak"
            ),
        },
    )


@app.get("/auth")
async def read_auth(
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    # Already logged-in users have no business on the auth page.
    user = await _optional_user(request, session)
    if user is not None:
        return RedirectResponse(url="/", status_code=302)
    return templates.TemplateResponse(request, "auth.html", {"user": None})


@app.get("/api/health/db")
async def health_db(session: AsyncSession = Depends(get_session)):
    # Simple connectivity check that exercises the session dependency.
    await session.execute(text("SELECT 1"))
    return {"database": "ok"}
