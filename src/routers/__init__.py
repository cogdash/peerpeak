"""Routers package - exports all API routers."""

from routers.auth import router as auth_router
from routers.profile import router as profile_router
from routers.feed import router as feed_router

__all__ = [
    "auth_router",
    "profile_router",
    "feed_router",
]
