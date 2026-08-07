"""User model."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import String, Text, DateTime, func, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.database import Base
from core.ids import generate_id

if TYPE_CHECKING:
    from models.badge import Badge
    from models.story import Story
    from models.session import Session
    from models.user_badge import UserBadge
    from models.user_story import UserStory
    from models.avatar import Avatar


class User(Base):
    __tablename__ = "user"

    id: Mapped[str] = mapped_column(
        String(24), primary_key=True, default=generate_id, index=True
    )
    name: Mapped[str] = mapped_column(
        String(100), unique=True, index=True, nullable=False
    )
    display_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    password: Mapped[str] = mapped_column(
        String(255), nullable=False
    )  # hashed password
    bio: Mapped[str | None] = mapped_column(Text, nullable=True)
    username_change_count: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    last_username_change: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
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
    badges: Mapped[list["UserBadge"]] = relationship(
        "UserBadge", back_populates="user", cascade="all, delete-orphan"
    )
    authored_badges: Mapped[list["Badge"]] = relationship(
        "Badge", back_populates="author", cascade="all, delete-orphan"
    )
    stories: Mapped[list["Story"]] = relationship(
        "Story", back_populates="author", cascade="all, delete-orphan"
    )
    sessions: Mapped[list["Session"]] = relationship(
        "Session", back_populates="user", cascade="all, delete-orphan"
    )
    liked_stories: Mapped[list["UserStory"]] = relationship(
        "UserStory", back_populates="user", cascade="all, delete-orphan"
    )
    avatar: Mapped["Avatar | None"] = relationship(
        "Avatar", back_populates="user", cascade="all, delete-orphan", uselist=False
    )

    def __repr__(self) -> str:
        return (
            f"<User(id={self.id}, name={self.name}, display_name={self.display_name})>"
        )
