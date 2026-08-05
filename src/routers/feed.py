"""Feed routes."""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from core.auth import get_current_user, require_auth, get_db
from core.dependencies import templates
from models import User

router = APIRouter()


@router.get("/feed", response_class=HTMLResponse)
def feed_page(request: Request, user: User = Depends(require_auth)):
    context = {"request": request, "user": user}
    return templates.TemplateResponse(request, "feed.html", context)


@router.get("/achievements")
def get_achievements():
    return "Bikepacking"
