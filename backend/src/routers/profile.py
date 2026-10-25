"""Badge endpoints: lookup, catalog and per-user badge management.

Badges live in a shared catalog (``badges``) and are attached to users through
``user_badges``. A badge title uniquely identifies a catalog entry, so adding an
already existing badge to a page only creates a ``user_badges`` row.
"""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from auth import get_current_user, get_optional_user
from classifier import classify
from db.models import Badge, Follow, User, UserBadge, normalize_title
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
    creator_username: str
    created_at: datetime
    # Users who marked the badge as received / added it to their page.
    received_count: int = 0
    users_count: int = 0


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
    # Users who marked the badge as received / added it to their page.
    received_count: int = 0
    users_count: int = 0


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


class FeedBadgeResponse(BaseModel):
    id: str
    title: str
    emoji: str
    polarity: str
    creator_username: str
    # How many users marked the badge as received.
    received_count: int
    # How many users have added the badge to their page.
    users_count: int


class FollowUserResponse(BaseModel):
    id: str
    username: str
    full_name: str
    # Whether the authenticated viewer follows this user.
    is_following: bool


class FollowStateResponse(BaseModel):
    following: bool
    followers_count: int


class UpdateEmojiRequest(BaseModel):
    emoji: str = Field(default="", max_length=16)


def _badge_response(
    badge: Badge,
    users_count: int = 0,
    received_count: int = 0,
) -> BadgeResponse:
    return BadgeResponse(
        id=str(badge.id),
        title=badge.title,
        emoji=badge.emoji,
        polarity=badge.polarity,
        creator_id=str(badge.creator_id),
        creator_username=badge.creator.username if badge.creator else "",
        created_at=badge.created_at,
        received_count=received_count,
        users_count=users_count,
    )


def _user_badge_response(
    user_badge: UserBadge,
    badge: Badge,
    user: User,
    users_count: int = 0,
    received_count: int = 0,
) -> UserBadgeResponse:
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
        received_count=received_count,
        users_count=users_count,
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


async def _get_user_by_username(session: AsyncSession, username: str) -> User | None:
    result = await session.execute(select(User).where(User.username == username))
    return result.scalar_one_or_none()


async def _followed_ids(
    session: AsyncSession,
    viewer_id: uuid.UUID,
    user_ids: list[uuid.UUID],
) -> set[uuid.UUID]:
    """Return the subset of ``user_ids`` that ``viewer_id`` follows."""
    if not user_ids:
        return set()

    result = await session.execute(
        select(Follow.following_id).where(
            Follow.follower_id == viewer_id,
            Follow.following_id.in_(user_ids),
        )
    )
    return set(result.scalars().all())


async def _badge_counts(
    session: AsyncSession,
    badge_ids: list[uuid.UUID],
) -> dict[uuid.UUID, tuple[int, int]]:
    """Return ``{badge_id: (users_count, received_count)}``."""
    if not badge_ids:
        return {}

    result = await session.execute(
        select(
            UserBadge.badge_id,
            func.count(UserBadge.id),
            func.count(UserBadge.id).filter(UserBadge.received.is_(True)),
        )
        .where(UserBadge.badge_id.in_(badge_ids))
        .group_by(UserBadge.badge_id)
    )
    return {
        badge_id: (int(total or 0), int(received or 0))
        for badge_id, total, received in result.all()
    }


async def _follow_counts(session: AsyncSession, user_id: uuid.UUID) -> tuple[int, int]:
    """Return ``(followers, following)`` counts for a user."""
    followers = await session.scalar(
        select(func.count())
        .select_from(Follow)
        .where(Follow.following_id == user_id)
    )
    following = await session.scalar(
        select(func.count())
        .select_from(Follow)
        .where(Follow.follower_id == user_id)
    )
    return int(followers or 0), int(following or 0)


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
        counts = await _badge_counts(session, [badge.id])
        return LookupResponse(
            title=title,
            polarity=badge.polarity,
            badge=_badge_response(badge, *counts.get(badge.id, (0, 0))),
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
    rows = result.all()
    counts = await _badge_counts(session, [badge.id for _, badge in rows])

    return [
        _user_badge_response(
            user_badge,
            badge,
            user,
            *counts.get(badge.id, (0, 0)),
        )
        for user_badge, badge in rows
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


@router.get("/feed/badges", response_model=list[FeedBadgeResponse])
async def feed_badges(
    limit: int = Query(default=10, ge=1, le=50),
    exclude_username: str | None = Query(default=None, min_length=1, max_length=32),
    session: AsyncSession = Depends(get_session),
) -> list[FeedBadgeResponse]:
    """Return a random selection of catalog badges for the discovery feed.

    This endpoint is public: the feed can be browsed without signing in.
    When ``exclude_username`` is passed, the database skips every badge that
    user already has on their page, so the feed only suggests something new.
    """
    users_count = (
        select(func.count(UserBadge.id))
        .where(UserBadge.badge_id == Badge.id)
        .correlate(Badge)
        .scalar_subquery()
    )
    received_count = (
        select(func.count(UserBadge.id))
        .where(
            UserBadge.badge_id == Badge.id,
            UserBadge.received.is_(True),
        )
        .correlate(Badge)
        .scalar_subquery()
    )

    statement = (
        select(
            Badge,
            users_count.label("users_count"),
            received_count.label("received_count"),
        )
        .options(selectinload(Badge.creator))
    )

    if exclude_username:
        owned = (
            select(UserBadge.badge_id)
            .join(User, User.id == UserBadge.user_id)
            .where(User.username == exclude_username)
        )
        statement = statement.where(Badge.id.notin_(owned))

    result = await session.execute(
        statement.order_by(func.random()).limit(limit)
    )

    return [
        FeedBadgeResponse(
            id=str(badge.id),
            title=badge.title,
            emoji=badge.emoji,
            polarity=badge.polarity,
            creator_username=badge.creator.username if badge.creator else "",
            received_count=int(received or 0),
            users_count=int(total or 0),
        )
        for badge, total, received in result.all()
    ]


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

    counts = await _badge_counts(session, [badge.id])
    return _user_badge_response(user_badge, badge, user, *counts.get(badge.id, (0, 0)))


@router.patch("/badges/{badge_id}")
async def update_badge_emoji(
    badge_id: uuid.UUID,
    payload: UpdateEmojiRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> BadgeResponse:
    """Update a badge icon. Only the badge creator may do this."""
    badge = await _get_badge_by_id(session, badge_id)
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

    counts = await _badge_counts(session, [badge.id])
    return _badge_response(badge, *counts.get(badge.id, (0, 0)))


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
    counts = await _badge_counts(session, [badge.id])
    return _user_badge_response(
        user_badge,
        badge,
        user,
        *counts.get(badge.id, (0, 0)),
    )


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
    counts = await _badge_counts(session, [badge.id])
    return _user_badge_response(
        user_badge,
        badge,
        user,
        *counts.get(badge.id, (0, 0)),
    )


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


@router.get("/badges/@{username}")
async def list_user_badges(
    username: str,
    session: AsyncSession = Depends(get_session),
) -> list[UserBadgeResponse]:
    """List every badge a specific user has added to their page.

    This endpoint is public and doesn't require authentication.
    """
    # Find the target user
    result = await session.execute(select(User).where(User.username == username))
    target_user = result.scalar_one_or_none()
    if target_user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Пользователь не найден",
        )

    result = await session.execute(
        select(UserBadge, Badge)
        .join(Badge, UserBadge.badge_id == Badge.id)
        .options(selectinload(Badge.creator))
        .where(UserBadge.user_id == target_user.id)
        .order_by(UserBadge.created_at.desc())
    )
    rows = result.all()
    counts = await _badge_counts(session, [badge.id for _, badge in rows])

    return [
        _user_badge_response(
            user_badge,
            badge,
            target_user,
            *counts.get(badge.id, (0, 0)),
        )
        for user_badge, badge in rows
    ]


@router.get("/badges/{badge_id}")
async def get_badge(
    badge_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> BadgeResponse:
    """Return a single badge from the catalog.

    This endpoint is public: a badge page can be opened without signing in.
    """
    badge = await _get_badge_by_id(session, badge_id)
    if badge is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Значок не найден",
        )

    counts = await _badge_counts(session, [badge.id])
    return _badge_response(badge, *counts.get(badge.id, (0, 0)))


@router.get("/users/@{username}")
async def get_user_profile(
    username: str,
    session: AsyncSession = Depends(get_session),
    viewer: User | None = Depends(get_optional_user),
):
    """Get a user's public profile information.

    This endpoint is public and doesn't require authentication. When the viewer
    is signed in, ``is_following`` tells whether they already follow the user.
    """
    target_user = await _get_user_by_username(session, username)
    if target_user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Пользователь не найден",
        )

    followers_count, following_count = await _follow_counts(session, target_user.id)

    is_following = False
    if viewer is not None and viewer.id != target_user.id:
        result = await session.scalar(
            select(func.count())
            .select_from(Follow)
            .where(
                Follow.follower_id == viewer.id,
                Follow.following_id == target_user.id,
            )
        )
        is_following = bool(result)

    return {
        "id": str(target_user.id),
        "username": target_user.username,
        "full_name": target_user.full_name,
        "bio": target_user.bio,
        "created_at": target_user.created_at,
        "followers_count": followers_count,
        "following_count": following_count,
        "is_following": is_following,
    }


@router.post("/users/{username}/follow", response_model=FollowStateResponse)
async def follow_user(
    username: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> FollowStateResponse:
    """Subscribe to a user. Repeated calls are idempotent."""
    target_user = await _get_user_by_username(session, username)
    if target_user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Пользователь не найден",
        )
    if target_user.id == user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Нельзя подписаться на себя",
        )

    if await session.get(Follow, (user.id, target_user.id)) is None:
        session.add(Follow(follower_id=user.id, following_id=target_user.id))
        await session.commit()

    followers_count, _ = await _follow_counts(session, target_user.id)
    return FollowStateResponse(following=True, followers_count=followers_count)


@router.delete("/users/{username}/follow", response_model=FollowStateResponse)
async def unfollow_user(
    username: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> FollowStateResponse:
    """Unsubscribe from a user. Repeated calls are idempotent."""
    target_user = await _get_user_by_username(session, username)
    if target_user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Пользователь не найден",
        )

    follow = await session.get(Follow, (user.id, target_user.id))
    if follow is not None:
        await session.delete(follow)
        await session.commit()

    followers_count, _ = await _follow_counts(session, target_user.id)
    return FollowStateResponse(following=False, followers_count=followers_count)


@router.get("/users/{username}/followers", response_model=list[FollowUserResponse])
async def list_followers(
    username: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[FollowUserResponse]:
    """List users following ``username``. Requires authentication."""
    target_user = await _get_user_by_username(session, username)
    if target_user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Пользователь не найден",
        )

    result = await session.execute(
        select(User)
        .join(Follow, Follow.follower_id == User.id)
        .where(Follow.following_id == target_user.id)
        .order_by(Follow.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    items = list(result.scalars().all())
    followed = await _followed_ids(session, user.id, [item.id for item in items])

    return [
        FollowUserResponse(
            id=str(item.id),
            username=item.username,
            full_name=item.full_name,
            is_following=item.id in followed,
        )
        for item in items
    ]


@router.get("/users/{username}/following", response_model=list[FollowUserResponse])
async def list_following(
    username: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[FollowUserResponse]:
    """List users followed by ``username``. Requires authentication."""
    target_user = await _get_user_by_username(session, username)
    if target_user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Пользователь не найден",
        )

    result = await session.execute(
        select(User)
        .join(Follow, Follow.following_id == User.id)
        .where(Follow.follower_id == target_user.id)
        .order_by(Follow.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    items = list(result.scalars().all())
    followed = await _followed_ids(session, user.id, [item.id for item in items])

    return [
        FollowUserResponse(
            id=str(item.id),
            username=item.username,
            full_name=item.full_name,
            is_following=item.id in followed,
        )
        for item in items
    ]

