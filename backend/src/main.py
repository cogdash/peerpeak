import os

from fastapi import Depends, FastAPI, Request
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from auth import get_current_user
from db.models import User
from db.session import get_session
from routers.auth import router as auth_router
from routers.profile import router as profile_router

app = FastAPI()

BASE_DIR = Path(__file__).resolve().parent

STATIC_DIR = BASE_DIR / "static"
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

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
    return FileResponse(STATIC_DIR / "profile.html")


@app.get("/profile")
async def read_profile(
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    # Unauthenticated visitors are sent straight to the auth page.
    user = await _optional_user(request, session)
    if user is None:
        return RedirectResponse(url="/auth", status_code=302)
    return FileResponse(STATIC_DIR / "profile.html")


@app.get("/auth")
async def read_auth(
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    # Already logged-in users have no business on the auth page.
    user = await _optional_user(request, session)
    if user is not None:
        return RedirectResponse(url="/", status_code=302)
    return FileResponse(STATIC_DIR / "auth.html")


@app.get("/api/health/db")
async def health_db(session: AsyncSession = Depends(get_session)):
    # Simple connectivity check that exercises the session dependency.
    await session.execute(text("SELECT 1"))
    return {"database": "ok"}
