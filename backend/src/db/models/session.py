import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import Base

# Session tokens live for 90 days from creation.
SESSION_TTL = timedelta(days=90)


def _default_expires_at() -> datetime:
    """Return the expiry timestamp for a freshly created session."""
    return datetime.now(tz=timezone.utc) + SESSION_TTL


class Session(Base):
    __tablename__ = "sessions"

    # The token itself is the primary key: a random UUID handed to the client.
    token: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
    )
    user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_default_expires_at,
    )

    user: Mapped["User"] = relationship(back_populates="sessions")

