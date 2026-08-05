"""Badge-Story association model."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import String, DateTime, ForeignKey, func, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.database import Base
from core.ids import generate_id

if TYPE_CHECKING:
    from models.badge import Badge
    from models.story import Story


class BadgeStory(Base):
    __tablename__ = "badge_story"

    id: Mapped[str] = mapped_column(
        String(24), primary_key=True, default=generate_id, index=True
    )
    badge_id: Mapped[str] = mapped_column(
        String(24),
        ForeignKey("badge.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    story_id: Mapped[str] = mapped_column(
        String(24),
        ForeignKey("story.id", ondelete="CASCADE"),
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
    badge: Mapped["Badge"] = relationship("Badge", back_populates="stories")
    story: Mapped["Story"] = relationship("Story", back_populates="badges")

    # Ensure a badge can only be linked to a story once
    __table_args__ = (UniqueConstraint("badge_id", "story_id", name="uq_badge_story"),)

    def __repr__(self) -> str:
        return f"<BadgeStory(badge_id={self.badge_id}, story_id={self.story_id})>"
