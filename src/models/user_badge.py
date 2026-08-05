"""User-Badge association model."""

from __future__ import annotations

from datetime import datetime
from enum import Enum as PyEnum
from typing import TYPE_CHECKING

from sqlalchemy import String, DateTime, ForeignKey, Enum, func, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.database import Base
from core.ids import generate_id

if TYPE_CHECKING:
    from models.user import User
    from models.badge import Badge


class UserBadgeStatus(PyEnum):
    """User's relationship to a badge."""

    STRIVES = "strives"  # User is working towards this badge
    HAS = "has"  # User has earned this badge
    NOT = "not"  # User explicitly doesn't have/want this badge


class UserBadge(Base):
    __tablename__ = "user_badge"

    id: Mapped[str] = mapped_column(
        String(24), primary_key=True, default=generate_id, index=True
    )
    user_id: Mapped[str] = mapped_column(
        String(24),
        ForeignKey("user.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    badge_id: Mapped[str] = mapped_column(
        String(24),
        ForeignKey("badge.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status: Mapped[UserBadgeStatus] = mapped_column(
        Enum(UserBadgeStatus, name="user_badge_status", create_constraint=True),
        nullable=False,
        default=UserBadgeStatus.NOT,
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
    user: Mapped["User"] = relationship("User", back_populates="badges")
    badge: Mapped["Badge"] = relationship("Badge", back_populates="user_badges")

    # Ensure a user can only have one status per badge
    __table_args__ = (UniqueConstraint("user_id", "badge_id", name="uq_user_badge"),)

    def __repr__(self) -> str:
        return f"<UserBadge(user_id={self.user_id}, badge_id={self.badge_id}, status={self.status.value})>"
