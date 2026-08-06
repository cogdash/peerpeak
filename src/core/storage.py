"""S3/MinIO storage utilities."""

import os
import uuid
from dataclasses import dataclass
from typing import Optional

import boto3
from botocore.config import Config


@dataclass
class PresignedPostData:
    """Data returned from generate_presigned_post."""

    url: str
    fields: dict
    key: str


class S3Storage:
    """S3/MinIO storage client for avatar uploads."""

    def __init__(self) -> None:
        self.endpoint_url = os.getenv("S3_ENDPOINT_URL")
        self.access_key = os.getenv("S3_ACCESS_KEY_ID")
        self.secret_key = os.getenv("S3_SECRET_ACCESS_KEY")
        self.bucket_name = os.getenv("S3_BUCKET_NAME", "peerpeak-user-content")
        self.region = os.getenv("S3_REGION", "us-east-1")
        self.public_url_base = os.getenv("S3_PUBLIC_URL_BASE")

        # Configure boto3 client
        self.client = boto3.client(
            "s3",
            endpoint_url=self.endpoint_url,
            aws_access_key_id=self.access_key,
            aws_secret_access_key=self.secret_key,
            region_name=self.region,
            config=Config(signature_version="s3v4"),
        )

    def generate_presigned_post(
        self,
        user_id: str,
        content_type: str,
        max_size: int = 5 * 1024 * 1024,  # 5MB
    ) -> PresignedPostData:
        """
        Generate a presigned POST for direct browser-to-S3 upload.

        Args:
            user_id: The user's ID
            content_type: The MIME type of the image (e.g., image/jpeg, image/png)
            max_size: Maximum file size in bytes (default 5MB)

        Returns:
            PresignedPostData with URL, fields, and the object key
        """
        # Validate content type is an image
        if not content_type.startswith("image/"):
            raise ValueError("Content type must be an image")

        # Generate unique key: avatars/{user_id}/original/{uuid}.{ext}
        ext = self._get_extension(content_type)
        key = f"avatars/{user_id}/original/{uuid.uuid4()}{ext}"

        # Conditions for the presigned POST
        conditions = [
            ["content-length-range", 0, max_size],
            ["starts-with", "$key", f"avatars/{user_id}/original/"],
            ["eq", "$Content-Type", content_type],
        ]

        # Generate presigned POST
        response = self.client.generate_presigned_post(
            Bucket=self.bucket_name,
            Key=key,
            Fields={"Content-Type": content_type},
            Conditions=conditions,
            ExpiresIn=3600,  # 1 hour
        )

        return PresignedPostData(
            url=response["url"],
            fields=response["fields"],
            key=key,
        )

    def get_public_url(self, key: str) -> str:
        """
        Get the public URL for an object.

        Args:
            key: The S3 object key

        Returns:
            Public URL for the object
        """
        if self.public_url_base:
            return f"{self.public_url_base.rstrip('/')}/{key}"

        if self.endpoint_url:
            # MinIO path-style URL
            return f"{self.endpoint_url.rstrip('/')}/{self.bucket_name}/{key}"

        # AWS S3 virtual-hosted-style URL
        return f"https://{self.bucket_name}.s3.{self.region}.amazonaws.com/{key}"

    def get_avatar_urls(self, user_id: str) -> dict[str, str]:
        """
        Get the public URLs for avatar variants.

        Args:
            user_id: The user's ID

        Returns:
            Dict with avatar_400 and avatar_100 URLs
        """
        return {
            "avatar_400": self.get_public_url(f"avatars/{user_id}/avatar_400.webp"),
            "avatar_100": self.get_public_url(f"avatars/{user_id}/avatar_100.webp"),
        }

    def object_exists(self, key: str) -> bool:
        """
        Check if an object exists in S3.

        Args:
            key: The S3 object key

        Returns:
            True if object exists, False otherwise
        """
        try:
            self.client.head_object(Bucket=self.bucket_name, Key=key)
            return True
        except self.client.exceptions.ClientError as e:
            if e.response["Error"]["Code"] == "404":
                return False
            raise

    def delete_objects(self, keys: list[str]) -> None:
        """
        Delete multiple objects from S3.

        Args:
            keys: List of S3 object keys to delete
        """
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
