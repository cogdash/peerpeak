"""S3/MinIO storage utilities for avatar handling."""

import os
import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING
from urllib.parse import urljoin

import boto3
from botocore.config import Config

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client


@dataclass
class PresignedPostData:
    """Data returned from generate_presigned_post."""

    url: str
    fields: dict
    key: str


class S3Storage:
    """S3/MinIO storage client for avatar uploads and management."""

    def __init__(self) -> None:
        self._client: "S3Client | None" = None

    @property
    def client(self) -> "S3Client":
        """Lazy initialization of boto3 S3 client."""
        if self._client is None:
            self._client = boto3.client(
                "s3",
                endpoint_url=os.getenv("S3_ENDPOINT_URL"),
                aws_access_key_id=os.getenv("S3_ACCESS_KEY_ID"),
                aws_secret_access_key=os.getenv("S3_SECRET_ACCESS_KEY"),
                region_name=os.getenv("S3_REGION", "us-east-1"),
                config=Config(signature_version="s3v4"),
            )
        return self._client

    @property
    def bucket_name(self) -> str:
        return os.getenv("S3_BUCKET_NAME", "peerpeak-user-content")

    @property
    def region(self) -> str:
        return os.getenv("S3_REGION", "us-east-1")

    @property
    def endpoint_url(self) -> str | None:
        return os.getenv("S3_ENDPOINT_URL")

    @property
    def public_url_base(self) -> str | None:
        return os.getenv("S3_PUBLIC_URL_BASE")

    def generate_presigned_post(
        self, user_id: str, content_type: str, max_size: int = 5 * 1024 * 1024
    ) -> PresignedPostData:
        """
        Generate a presigned POST for direct browser-to-S3 upload.

        Args:
            user_id: The user's ID
            content_type: The MIME type of the image (e.g., "image/jpeg")
            max_size: Maximum file size in bytes (default 5MB)

        Returns:
            PresignedPostData with URL, fields, and the object key
        """
        # Validate content type is an image
        if not content_type.startswith("image/"):
            raise ValueError("Content type must be an image")

        # Determine file extension from content type
        ext = self._get_extension(content_type)

        # Generate unique key: avatars/{user_id}/original/{uuid}.{ext}
        key = f"avatars/{user_id}/original/{uuid.uuid4()}{ext}"

        conditions = [
            ["content-length-range", 0, max_size],
            ["starts-with", "$key", f"avatars/{user_id}/original/"],
            ["eq", "$Content-Type", content_type],
        ]

        presigned = self.client.generate_presigned_post(
            Bucket=self.bucket_name,
            Key=key,
            Fields={"Content-Type": content_type},
            Conditions=conditions,
            ExpiresIn=3600,  # 1 hour
        )

        return PresignedPostData(
            url=presigned["url"],
            fields=presigned["fields"],
            key=key,
        )

    def get_public_url(self, key: str) -> str:
        """Get the public URL for an S3 object."""
        if self.public_url_base:
            return urljoin(self.public_url_base.rstrip("/") + "/", key)
        if self.endpoint_url:
            # MinIO local development
            return f"{self.endpoint_url.rstrip('/')}/{self.bucket_name}/{key}"
        # AWS S3
        return f"https://{self.bucket_name}.s3.{self.region}.amazonaws.com/{key}"

    def get_avatar_urls(self, user_id: str) -> dict[str, str]:
        """Get public URLs for avatar variants."""
        return {
            "avatar_400": self.get_public_url(f"avatars/{user_id}/avatar_400.webp"),
            "avatar_100": self.get_public_url(f"avatars/{user_id}/avatar_100.webp"),
        }

    def object_exists(self, key: str) -> bool:
        """Check if an object exists in S3 (HEAD request)."""
        try:
            self.client.head_object(Bucket=self.bucket_name, Key=key)
            return True
        except self.client.exceptions.ClientError as e:
            if e.response["Error"]["Code"] == "404":
                return False
            raise

    def delete_objects(self, keys: list[str]) -> None:
        """Delete multiple objects from S3."""
        if not keys:
            return

        objects = [{"Key": key} for key in keys]
        self.client.delete_objects(Bucket=self.bucket_name, Delete={"Objects": objects})

    def _get_extension(self, content_type: str) -> str:
        """Get file extension from content type."""
        extensions = {
            "image/jpeg": ".jpg",
            "image/png": ".png",
            "image/webp": ".webp",
            "image/gif": ".gif",
            "image/bmp": ".bmp",
            "image/tiff": ".tiff",
        }
        return extensions.get(content_type, ".bin")


# Global instance
storage = S3Storage()
