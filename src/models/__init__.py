"""Models package - exports all SQLAlchemy models."""

from core.database import Base

# Import all models to register them with Base.metadata
from models.user import User
from models.badge import Badge, BadgeType
from models.story import Story
from models.session import Session
from models.user_badge import UserBadge, UserBadgeStatus
from models.badge_story import BadgeStory
from models.user_story import UserStory

__all__ = [
    "Base",
    "User",
    "Badge",
    "BadgeType",
    "Story",
    "Session",
    "UserBadge",
    "UserBadgeStatus",
    "BadgeStory",
    "UserStory",
]
