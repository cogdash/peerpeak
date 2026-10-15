"""Badge endpoints: lookup, catalog and per-user badge management.

Badges live in a shared catalog (``badges``) and are attached to users through
``user_badges``. A badge title uniquely identifies a catalog entry, so adding an
already existing badge to a page only creates a ``user_badges`` row.
"""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from auth import get_current_user
from classifier import classify
from db.models import Badge, User, UserBadge, normalize_title
from db.session import get_session

router = APIRouter(prefix="/api", tags=["profile"])

# Emoji used when a badge is created without an explicit icon.
DEFAULT_EMOJI = {"positive": "🏆", "negative": "💀"}
VALID_POLARITIES = ("positive", "negative")

def _normalize_polarity(raw: str | None) -> str | None:
    """Return a valid polarity or ``None`` when the value is unusable."""
    if raw in VALID_POLARITIES:
        return raw
    return None


class BadgeResponse(BaseModel):
    id: str
    title: str
    emoji: str
    polarity: str
    creator_id: str
    created_at: datetime


class UserBadgeResponse(BaseModel):
    id: str
    badge_id: str
    title: str
    emoji: str
    polarity: str
    received: bool
    received_at: datetime | None
    is_creator: bool
    # Username of the badge creator, shown as "by @user" on the card.
    creator_username: str
    created_at: datetime


class LookupResponse(BaseModel):
    title: str
    polarity: str
    badge: BadgeResponse | None
    score: float
    scores: dict[str, float]


class AddBadgeRequest(BaseModel):
    title: str = Field(min_length=1, max_length=50)
    emoji: str = Field(default="", max_length=16)
    polarity: str | None = None
    received: bool = False


class UpdateEmojiRequest(BaseModel):
    emoji: str = Field(default="", max_length=16)


def _badge_response(badge: Badge) -> BadgeResponse:
    return BadgeResponse(
        id=str(badge.id),
        title=badge.title,
        emoji=badge.emoji,
        polarity=badge.polarity,
        creator_id=str(badge.creator_id),
        created_at=badge.created_at,
    )


def _user_badge_response(user_badge: UserBadge, badge: Badge, user: User) -> UserBadgeResponse:
    return UserBadgeResponse(
        id=str(user_badge.id),
        badge_id=str(badge.id),
        title=badge.title,
        emoji=badge.emoji,
        polarity=badge.polarity,
        received=user_badge.received,
        received_at=user_badge.received_at,
        is_creator=badge.creator_id == user.id,
        creator_username=badge.creator.username if badge.creator else "",
        created_at=user_badge.created_at,
    )


async def _get_badge_by_title(session: AsyncSession, title: str) -> Badge | None:
    # Eager-load the creator so responses can read ``badge.creator.username``
    # without triggering a lazy load outside the async context.
    result = await session.execute(
        select(Badge)
        .options(selectinload(Badge.creator))
        .where(Badge.title == title)
    )
    return result.scalar_one_or_none()


async def _get_badge_by_id(session: AsyncSession, badge_id: uuid.UUID) -> Badge | None:
    # Same eager-loading rationale as ``_get_badge_by_title``.
    result = await session.execute(
        select(Badge)
        .options(selectinload(Badge.creator))
        .where(Badge.id == badge_id)
    )
    return result.scalar_one_or_none()


@router.get("/badge/lookup")
async def lookup_badge(
    text: str = Query(..., min_length=1, max_length=500),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> LookupResponse:
    """Return the polarity of a badge and the existing catalog entry, if any.

    When the normalized title already exists in the catalog its stored polarity
    is authoritative; otherwise the text is classified on the fly.
    """
    title = normalize_title(text)
    if not title:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Текст значка не может быть пустым",
        )

    badge = await _get_badge_by_title(session, title)
    if badge is not None:
        return LookupResponse(
            title=title,
            polarity=badge.polarity,
            badge=_badge_response(badge),
            score=1.0,
            scores={},
        )

    result = await classify(text)
    polarity = _normalize_polarity(result["label"]) or "positive"

    return LookupResponse(
        title=title,
        polarity=polarity,
        badge=None,
        score=result["score"],
        scores=result["scores"],
    )


@router.get("/badges")
async def list_badges(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[UserBadgeResponse]:
    """List every badge the current user has added to their page."""
    result = await session.execute(
        select(UserBadge, Badge)
        .join(Badge, UserBadge.badge_id == Badge.id)
        .options(selectinload(Badge.creator))
        .where(UserBadge.user_id == user.id)
        .order_by(UserBadge.created_at.desc())
    )

    return [
        _user_badge_response(user_badge, badge, user)
        for user_badge, badge in result.all()
    ]


@router.get("/badges/catalog")
async def list_catalog(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[str]:
    """Return every badge title in the shared catalog.

    Used by the frontend to build a placeholder hint from the whole catalog
    (across all users), not just the current user's page.
    """
    result = await session.execute(select(Badge.title).order_by(Badge.title))
    return list(result.scalars().all())


@router.post("/badges", status_code=status.HTTP_201_CREATED)
async def add_badge(
    payload: AddBadgeRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> UserBadgeResponse:
    """Add a badge to the current user's page.

    If a badge with the same normalized title already exists it is reused and
    only a ``user_badges`` row is created; otherwise a new catalog entry is
    created with the current user as its creator.
    """
    title = normalize_title(payload.title)
    if not title:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Текст значка не может быть пустым",
        )

    badge = await _get_badge_by_title(session, title)

    if badge is None:
        polarity = _normalize_polarity(payload.polarity)
        if polarity is None:
            result = await classify(payload.title)
            polarity = _normalize_polarity(result["label"]) or "positive"

        badge = Badge(
            title=title,
            emoji=payload.emoji or DEFAULT_EMOJI[polarity],
            polarity=polarity,
            creator_id=user.id,
        )
        # Populate the relationship in-memory so the response can read
        # ``badge.creator.username`` without a lazy load.
        badge.creator = user
        session.add(badge)
        await session.flush()

    existing = await session.execute(
        select(UserBadge).where(
            UserBadge.user_id == user.id,
            UserBadge.badge_id == badge.id,
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Этот значок уже добавлен на вашу страницу",
        )

    user_badge = UserBadge(
        user_id=user.id,
        badge_id=badge.id,
        received=payload.received,
        received_at=datetime.now(tz=timezone.utc) if payload.received else None,
    )
    session.add(user_badge)
    await session.commit()
    await session.refresh(user_badge)

    return _user_badge_response(user_badge, badge, user)


@router.patch("/badges/{badge_id}")
async def update_badge_emoji(
    badge_id: uuid.UUID,
    payload: UpdateEmojiRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> BadgeResponse:
    """Update a badge icon. Only the badge creator may do this."""
    badge = await session.get(Badge, badge_id)
    if badge is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Значок не найден",
        )

    if badge.creator_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Менять иконку может только создатель значка",
        )

    badge.emoji = payload.emoji
    await session.commit()
    await session.refresh(badge)

    return _badge_response(badge)


@router.post("/user-badges/{user_badge_id}/receive")
async def receive_badge(
    user_badge_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> UserBadgeResponse:
    """Mark a badge on the current user's page as received."""
    user_badge = await session.get(UserBadge, user_badge_id)
    if user_badge is None or user_badge.user_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Значок не найден",
        )

    if not user_badge.received:
        user_badge.received = True
        user_badge.received_at = datetime.now(tz=timezone.utc)
        await session.commit()
        await session.refresh(user_badge)

    badge = await _get_badge_by_id(session, user_badge.badge_id)
    return _user_badge_response(user_badge, badge, user)


@router.post("/user-badges/{user_badge_id}/unreceive")
async def unreceive_badge(
    user_badge_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> UserBadgeResponse:
    """Cancel the received state of a badge on the current user's page."""
    user_badge = await session.get(UserBadge, user_badge_id)
    if user_badge is None or user_badge.user_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Значок не найден",
        )

    if user_badge.received:
        user_badge.received = False
        user_badge.received_at = None
        await session.commit()
        await session.refresh(user_badge)

    badge = await _get_badge_by_id(session, user_badge.badge_id)
    return _user_badge_response(user_badge, badge, user)


@router.delete("/user-badges/{user_badge_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_user_badge(
    user_badge_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> None:
    """Remove a badge from the current user's page."""
    user_badge = await session.get(UserBadge, user_badge_id)
    if user_badge is None or user_badge.user_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Значок не найден",
        )

    await session.delete(user_badge)
    await session.commit()

