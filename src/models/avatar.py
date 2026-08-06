"""Avatar model."""

from __future__ import annotations

from datetime import datetime
from enum import Enum as PyEnum
from typing import TYPE_CHECKING

from sqlalchemy import (
    String,
    Text,
    DateTime,
    func,
    Integer,
    ForeignKey,
    Enum as SQLEnum,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.database import Base
from core.ids import generate_id

if TYPE_CHECKING:
    from models.user import User


class AvatarStatus(str, PyEnum):
    """Avatar processing status."""

    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


class Avatar(Base):
    __tablename__ = "avatar"

    id: Mapped[str] = mapped_column(
        String(24), primary_key=True, default=generate_id, index=True
    )
    user_id: Mapped[str] = mapped_column(
        String(24),
        ForeignKey("user.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
    )
    original_key: Mapped[str] = mapped_column(String(512), nullable=False)
    avatar_400_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    avatar_100_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[AvatarStatus] = mapped_column(
        SQLEnum(AvatarStatus, name="avatar_status", create_constraint=True),
        default=AvatarStatus.PROCESSING,
        nullable=False,
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

    # Relationship
    user: Mapped["User"] = relationship("User", back_populates="avatar")

    def __repr__(self) -> str:
        return f"<Avatar(id={self.id}, user_id={self.user_id}, status={self.status})>"
