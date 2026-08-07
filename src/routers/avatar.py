"""Avatar API endpoints."""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from core.auth import get_db, require_auth_api
from core.dependencies import get_storage
from core.storage import S3Storage
from models import User, Avatar, AvatarStatus

router = APIRouter(prefix="/api/avatar", tags=["avatar"])


class PresignRequest(BaseModel):
    """Request model for presigned POST generation."""

    content_type: str


class PresignResponse(BaseModel):
    """Response model for presigned POST generation."""

    url: str
    fields: dict
    key: str


class CompleteRequest(BaseModel):
    """Request model for avatar upload completion."""

    key: str


class CompleteResponse(BaseModel):
    """Response model for avatar upload completion."""

    status: str


class AvatarResponse(BaseModel):
    """Response model for avatar status and URLs."""

    status: str
    avatar_400: str | None = None
    avatar_100: str | None = None


class DeleteResponse(BaseModel):
    """Response model for avatar deletion."""

    message: str


@router.post("/presign", response_model=PresignResponse)
def presign_avatar(
    request: PresignRequest,
    user: User = Depends(require_auth_api),
    storage: S3Storage = Depends(get_storage),
) -> PresignResponse:
    """
    Generate a presigned POST for direct browser-to-S3 upload.

    Args:
        request: Contains the content_type of the image to upload
        user: The authenticated user
        storage: S3Storage instance

    Returns:
        PresignedPostData with URL, fields, and the object key

    Raises:
        HTTPException: If content type is not an image
    """
    try:
        presigned_data = storage.generate_presigned_post(
            user_id=user.id, content_type=request.content_type
        )
        return PresignResponse(
            url=presigned_data.url,
            fields=presigned_data.fields,
            key=presigned_data.key,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.post("/complete", response_model=CompleteResponse)
def complete_avatar(
    request: CompleteRequest,
    user: User = Depends(require_auth_api),
    db: Session = Depends(get_db),
) -> CompleteResponse:
    """
    Called after successful S3 upload to create avatar record.

    Args:
        request: Contains the S3 key of the uploaded original
        user: The authenticated user
        db: Database session

    Returns:
        Status indicating processing has started

    Raises:
        HTTPException: If key doesn't belong to user
    """
    # Validate key belongs to this user
    expected_prefix = f"avatars/{user.id}/original/"
    if not request.key.startswith(expected_prefix):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid key for this user",
        )

    # Create avatar record with processing status
    avatar = Avatar(
        user_id=user.id,
        original_key=request.key,
        content_type="",  # Will be filled by Lambda
        file_size=0,  # Will be filled by Lambda
        status=AvatarStatus.PROCESSING,
    )
    db.add(avatar)
    db.commit()

    return CompleteResponse(status="processing")


@router.get("/me", response_model=AvatarResponse)
def get_avatar(
    user: User = Depends(require_auth_api),
    db: Session = Depends(get_db),
    storage: S3Storage = Depends(get_storage),
) -> AvatarResponse:
    """
    Get current avatar variant URLs.

    Args:
        user: The authenticated user
        db: Database session
        storage: S3Storage instance

    Returns:
        Avatar status and URLs for variants
    """
    avatar = db.query(Avatar).filter(Avatar.user_id == user.id).first()

    if not avatar:
        return AvatarResponse(status="none")

    # DEBUG
    print(f"DEBUG: avatar={avatar}")
    print(f"DEBUG: avatar.status={avatar.status}")
    print(
        f"DEBUG: avatar.status == AvatarStatus.PROCESSING: {avatar.status == AvatarStatus.PROCESSING}"
    )
    print(
        f"DEBUG: avatar.status == AvatarStatus.FAILED: {avatar.status == AvatarStatus.FAILED}"
    )
    print(
        f"DEBUG: avatar.status == AvatarStatus.READY: {avatar.status == AvatarStatus.READY}"
    )
    print(f"DEBUG: avatar.avatar_400_key={avatar.avatar_400_key}")
    print(f"DEBUG: avatar.avatar_100_key={avatar.avatar_100_key}")

    if avatar.status == AvatarStatus.PROCESSING:
        return AvatarResponse(status="processing")

    if avatar.status == AvatarStatus.FAILED:
        return AvatarResponse(status="failed")

    # Status is READY - check if variant objects exist in S3
    print(
        f"DEBUG: About to call storage.object_exists for avatar_400_key={avatar.avatar_400_key}"
    )
    avatar_400_exists = (
        storage.object_exists(avatar.avatar_400_key) if avatar.avatar_400_key else False
    )
    print(
        f"DEBUG: Called storage.object_exists for avatar_400_key, result={avatar_400_exists}"
    )
    print(
        f"DEBUG: About to call storage.object_exists for avatar_100_key={avatar.avatar_100_key}"
    )
    avatar_100_exists = (
        storage.object_exists(avatar.avatar_100_key) if avatar.avatar_100_key else False
    )
    print(
        f"DEBUG: Called storage.object_exists for avatar_100_key, result={avatar_100_exists}"
    )

    print(f"DEBUG: avatar_400_exists={avatar_400_exists}")
    print(f"DEBUG: avatar_100_exists={avatar_100_exists}")

    if not avatar_400_exists or not avatar_100_exists:
        # Variants not yet in S3, still processing
        return AvatarResponse(status="processing")

    urls = storage.get_avatar_urls(user.id)
    return AvatarResponse(
        status="ready",
        avatar_400=urls["avatar_400"],
        avatar_100=urls["avatar_100"],
    )


@router.delete("/me", response_model=DeleteResponse)
def delete_avatar(
    user: User = Depends(require_auth_api),
    db: Session = Depends(get_db),
    storage: S3Storage = Depends(get_storage),
) -> DeleteResponse:
    """
    Remove avatar and all associated S3 objects.

    Args:
        user: The authenticated user
        db: Database session
        storage: S3Storage instance

    Returns:
        Success message

    Raises:
        HTTPException: If no avatar found
    """
    avatar = db.query(Avatar).filter(Avatar.user_id == user.id).first()

    if not avatar:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No avatar found",
        )

    # Collect all keys to delete
    keys_to_delete = [avatar.original_key]
    if avatar.avatar_400_key:
        keys_to_delete.append(avatar.avatar_400_key)
    if avatar.avatar_100_key:
        keys_to_delete.append(avatar.avatar_100_key)

    # Delete from S3
    storage.delete_objects(keys_to_delete)

    # Delete avatar record (cascades to user relationship)
    db.delete(avatar)
    db.commit()

    return DeleteResponse(message="Avatar deleted successfully")
