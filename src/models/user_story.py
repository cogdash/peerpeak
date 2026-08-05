"""User-Story association model."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import String, DateTime, ForeignKey, Boolean, func, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.database import Base
from core.ids import generate_id

if TYPE_CHECKING:
    from models.user import User
    from models.story import Story


class UserStory(Base):
    __tablename__ = "user_story"

    id: Mapped[str] = mapped_column(
        String(24), primary_key=True, default=generate_id, index=True
    )
    user_id: Mapped[str] = mapped_column(
        String(24),
        ForeignKey("user.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    story_id: Mapped[str] = mapped_column(
        String(24),
        ForeignKey("story.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    liked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
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
    user: Mapped["User"] = relationship("User", back_populates="liked_stories")
    story: Mapped["Story"] = relationship("Story", back_populates="user_interactions")

    # Ensure a user can only like a story once
    __table_args__ = (UniqueConstraint("user_id", "story_id", name="uq_user_story"),)

    def __repr__(self) -> str:
        return f"<UserStory(user_id={self.user_id}, story_id={self.story_id}, liked={self.liked})>"
