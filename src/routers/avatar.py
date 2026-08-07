"""Avatar API routes."""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from core.auth import get_db, require_auth
from core.storage import S3Storage
from models import Avatar, AvatarStatus, User

router = APIRouter(prefix="/api/avatar", tags=["avatar"])


class PresignRequest(BaseModel):
    content_type: str


class PresignResponse(BaseModel):
    url: str
    fields: dict
    key: str


class CompleteRequest(BaseModel):
    key: str


class CompleteResponse(BaseModel):
    status: str


class AvatarResponse(BaseModel):
    status: str
    avatar_400: str | None = None
    avatar_100: str | None = None


def get_storage() -> S3Storage:
    """Dependency to get S3Storage instance."""
    return S3Storage()


@router.post("/presign", response_model=PresignResponse)
def presign_avatar_upload(
    request: PresignRequest,
    user: User = Depends(require_auth),
    storage: S3Storage = Depends(get_storage),
) -> PresignResponse:
    """
    Generate a presigned POST for direct browser-to-S3 avatar upload.

    Args:
        request: Contains the content_type of the image to upload
        user: Authenticated user (from session)
        storage: S3Storage instance

    Returns:
        Presigned POST data (url, fields, key)
    """
    # Validate content type is an image
    if not request.content_type.startswith("image/"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Content type must be an image",
        )

    # Generate presigned POST
    presigned = storage.generate_presigned_post(user.id, request.content_type)

    return PresignResponse(
        url=presigned.url,
        fields=presigned.fields,
        key=presigned.key,
    )


@router.post("/complete", response_model=CompleteResponse)
def complete_avatar_upload(
    request: CompleteRequest,
    user: User = Depends(require_auth),
    db: Session = Depends(get_db),
    storage: S3Storage = Depends(get_storage),
) -> CompleteResponse:
    """
    Complete avatar upload after successful S3 upload.

    Creates an Avatar record with status="processing".
    The Lambda function will process the image and update the record.

    Args:
        request: Contains the S3 key of the uploaded original
        user: Authenticated user
        db: Database session
        storage: S3Storage instance

    Returns:
        Status indicating processing has started
    """
    # Validate the key belongs to this user
    if not request.key.startswith(f"avatars/{user.id}/original/"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid key for this user",
        )

    # Check if user already has an avatar
    existing_avatar = db.query(Avatar).filter(Avatar.user_id == user.id).first()
    if existing_avatar:
        # Delete old S3 objects
        keys_to_delete = [
            existing_avatar.original_key,
        ]
        if existing_avatar.avatar_400_key:
            keys_to_delete.append(existing_avatar.avatar_400_key)
        if existing_avatar.avatar_100_key:
            keys_to_delete.append(existing_avatar.avatar_100_key)
        storage.delete_objects(keys_to_delete)
        db.delete(existing_avatar)

    # Create new avatar record
    avatar = Avatar(
        user_id=user.id,
        original_key=request.key,
        content_type="image/jpeg",  # Will be updated by Lambda
        file_size=0,  # Will be updated by Lambda
        status=AvatarStatus.PROCESSING,
    )
    db.add(avatar)
    db.commit()

    return CompleteResponse(status="processing")


@router.get("/me", response_model=AvatarResponse)
def get_my_avatar(
    user: User = Depends(require_auth),
    db: Session = Depends(get_db),
    storage: S3Storage = Depends(get_storage),
) -> AvatarResponse:
    """
    Get current user's avatar variant URLs.

    Checks S3 for the existence of processed variants.

    Args:
        user: Authenticated user
        db: Database session
        storage: S3Storage instance

    Returns:
        Avatar status and variant URLs if ready
    """
    avatar = db.query(Avatar).filter(Avatar.user_id == user.id).first()

    if not avatar:
        return AvatarResponse(status="none")

    if avatar.status == AvatarStatus.PROCESSING:
        # Check if variants exist in S3 (Lambda may have completed)
        avatar_400_key = f"avatars/{user.id}/avatar_400.webp"
        avatar_100_key = f"avatars/{user.id}/avatar_100.webp"

        if storage.object_exists(avatar_400_key) and storage.object_exists(
            avatar_100_key
        ):
            # Update avatar record
            avatar.status = AvatarStatus.READY
            avatar.avatar_400_key = avatar_400_key
            avatar.avatar_100_key = avatar_100_key
            db.commit()

            urls = storage.get_avatar_urls(user.id)
            return AvatarResponse(
                status="ready",
                avatar_400=urls["avatar_400"],
                avatar_100=urls["avatar_100"],
            )

        return AvatarResponse(status="processing")

    if avatar.status == AvatarStatus.READY:
        urls = storage.get_avatar_urls(user.id)
        return AvatarResponse(
            status="ready",
            avatar_400=urls["avatar_400"],
            avatar_100=urls["avatar_100"],
        )

    return AvatarResponse(status="failed")


@router.delete("/me")
def delete_my_avatar(
    user: User = Depends(require_auth),
    db: Session = Depends(get_db),
    storage: S3Storage = Depends(get_storage),
) -> dict:
    """
    Delete current user's avatar.

    Removes all S3 objects and the Avatar record.

    Args:
        user: Authenticated user
        db: Database session
        storage: S3Storage instance

    Returns:
        Success message
    """
    avatar = db.query(Avatar).filter(Avatar.user_id == user.id).first()

    if not avatar:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No avatar found",
        )

    # Delete S3 objects
    keys_to_delete = [avatar.original_key]
    if avatar.avatar_400_key:
        keys_to_delete.append(avatar.avatar_400_key)
    if avatar.avatar_100_key:
        keys_to_delete.append(avatar.avatar_100_key)

    storage.delete_objects(keys_to_delete)

    # Delete avatar record
    db.delete(avatar)
    db.commit()

    return {"message": "Avatar deleted successfully"}
