import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import Base

# A badge title is limited to the same length the UI enforces.
MAX_TITLE_LENGTH = 50


def normalize_title(title: str) -> str:
    """Normalize a badge title for storage and lookup.

    Titles are case-insensitive and the letter "ё" is folded to "е", so that
    "Ёлка" and "елка" refer to the same badge. Whitespace is collapsed and
    trimmed, and the result is capped at ``MAX_TITLE_LENGTH`` characters.
    """
    folded = title.lower().replace("ё", "е")
    collapsed = " ".join(folded.split())
    return collapsed[:MAX_TITLE_LENGTH]


class Badge(Base):
    """A badge in the global catalog.

    Badges are shared between users: the ``title`` uniquely identifies a badge
    across the whole table, so adding an already existing badge to a page only
    creates a ``user_badges`` row instead of a new badge.
    """

    __tablename__ = "badges"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    # Stored normalized (lowercase, no "ё"), which makes a plain unique
    # constraint behave case-insensitively.
    title: Mapped[str] = mapped_column(
        String(MAX_TITLE_LENGTH),
        unique=True,
        index=True,
    )
    emoji: Mapped[str] = mapped_column(String(16), default="")
    # "positive" for achievements, "negative" for anti-achievements.
    polarity: Mapped[str] = mapped_column(String(16), default="positive")
    creator_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    creator: Mapped["User"] = relationship(back_populates="created_badges")
    user_badges: Mapped[list["UserBadge"]] = relationship(
        back_populates="badge",
        cascade="all, delete-orphan",
    )

