"""Badge model."""

from __future__ import annotations

from datetime import datetime
from enum import Enum as PyEnum
from typing import TYPE_CHECKING

from sqlalchemy import String, Text, DateTime, ForeignKey, Enum, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.database import Base
from core.ids import generate_id

if TYPE_CHECKING:
    from models.user import User
    from models.user_badge import UserBadge
    from models.badge_story import BadgeStory


class BadgeType(PyEnum):
    """Badge type: fame (achievement) or shame (failure)."""

    FAME = "fame"
    SHAME = "shame"


class Badge(Base):
    __tablename__ = "badge"

    id: Mapped[str] = mapped_column(
        String(24), primary_key=True, default=generate_id, index=True
    )
    name: Mapped[str] = mapped_column(String(200), index=True, nullable=False)
    badge_type: Mapped[BadgeType] = mapped_column(
        Enum(BadgeType, name="badge_type", create_constraint=True),
        nullable=False,
        default=BadgeType.FAME,
    )
    author_id: Mapped[str] = mapped_column(
        String(24),
        ForeignKey("user.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    author: Mapped["User"] = relationship("User", back_populates="authored_badges")
    user_badges: Mapped[list["UserBadge"]] = relationship(
        "UserBadge", back_populates="badge", cascade="all, delete-orphan"
    )
    stories: Mapped[list["BadgeStory"]] = relationship(
        "BadgeStory", back_populates="badge", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Badge(id={self.id}, name={self.name}, type={self.badge_type.value})>"
