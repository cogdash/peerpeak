"""AWS Lambda function for avatar image processing.

Triggered by S3 ObjectCreated events on avatars/*/original/*
Processes images and generates WebP thumbnails at 400px and 100px.
"""

import io
import os
import urllib.parse
from typing import Any

import boto3
from PIL import Image

# Initialize S3 client
s3 = boto3.client("s3")

# Configuration from environment
BUCKET_NAME = os.getenv("S3_BUCKET_NAME", "peerpeak-user-content")
AVATAR_400_SIZE = (400, 400)
AVATAR_100_SIZE = (100, 100)
WEBP_QUALITY_400 = 85
WEBP_QUALITY_100 = 80


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Process S3 event and generate avatar thumbnails.

    Args:
        event: S3 event notification
        context: Lambda context

    Returns:
        Response dict with status
    """
    print(f"Received event: {event}")

    for record in event.get("Records", []):
        try:
            process_record(record)
        except Exception as e:
            print(f"Error processing record: {e}")
            # Don't re-raise to avoid retry loops for unprocessable images
            # The original file remains for manual inspection

    return {"statusCode": 200, "body": "Processing complete"}


def process_record(record: dict[str, Any]) -> None:
    """Process a single S3 event record.

    Args:
        record: S3 event record
    """
    # Extract bucket and key from event
    bucket = record["s3"]["bucket"]["name"]
    key = urllib.parse.unquote_plus(record["s3"]["object"]["key"])

    print(f"Processing: s3://{bucket}/{key}")

    # Validate key format: avatars/{user_id}/original/{uuid}.{ext}
    if not key.startswith("avatars/") or "/original/" not in key:
        print(f"Skipping non-avatar key: {key}")
        return

    # Extract user_id from key
    # Format: avatars/{user_id}/original/{filename}
    parts = key.split("/")
    if len(parts) < 4:
        print(f"Invalid key format: {key}")
        return

    user_id = parts[1]
    print(f"Processing avatar for user: {user_id}")

    # Download original image from S3
    response = s3.get_object(Bucket=bucket, Key=key)
    image_data = response["Body"].read()
    content_type = response.get("ContentType", "")
    file_size = len(image_data)

    print(f"Downloaded {file_size} bytes, content-type: {content_type}")

    # Validate and convert image
    try:
        image = validate_and_convert_image(image_data)
    except ValueError as e:
        print(f"Invalid image: {e}")
        # Delete the invalid original
        s3.delete_object(Bucket=bucket, Key=key)
        return

    # Generate thumbnails
    avatar_400_key = f"avatars/{user_id}/avatar_400.webp"
    avatar_100_key = f"avatars/{user_id}/avatar_100.webp"

    # Generate 400x400 WebP
    avatar_400_data = generate_thumbnail(image, AVATAR_400_SIZE, WEBP_QUALITY_400)
    print(f"Generated 400px thumbnail: {len(avatar_400_data)} bytes")

    # Generate 100x100 WebP
    avatar_100_data = generate_thumbnail(image, AVATAR_100_SIZE, WEBP_QUALITY_100)
    print(f"Generated 100px thumbnail: {len(avatar_100_data)} bytes")

    # Upload variants (atomic overwrite)
    s3.put_object(
        Bucket=bucket,
        Key=avatar_400_key,
        Body=avatar_400_data,
        ContentType="image/webp",
        CacheControl="public, max-age=31536000, immutable",
    )
    print(f"Uploaded: s3://{bucket}/{avatar_400_key}")

    s3.put_object(
        Bucket=bucket,
        Key=avatar_100_key,
        Body=avatar_100_data,
        ContentType="image/webp",
        CacheControl="public, max-age=31536000, immutable",
    )
    print(f"Uploaded: s3://{bucket}/{avatar_100_key}")

    # Delete original after successful variant upload
    s3.delete_object(Bucket=bucket, Key=key)
    print(f"Deleted original: s3://{bucket}/{key}")

    print(f"Successfully processed avatar for user {user_id}")


import io
from PIL import Image


def validate_and_convert_image(image_data: bytes) -> Image.Image:
    """Validate image data and convert to RGB mode.

    Args:
        image_data: Raw image bytes

    Returns:
        PIL Image in RGB mode

    Raises:
        ValueError: If image is invalid or unsupported format
    """
    try:
        image = Image.open(io.BytesIO(image_data))
        image.load()  # Force load to validate
    except Exception as e:
        raise ValueError(f"Cannot open image: {e}")

    # Check format
    if image.format not in ("JPEG", "PNG", "WEBP", "GIF", "BMP", "TIFF"):
        raise ValueError(f"Unsupported image format: {image.format}")

    # Convert to RGB (removes alpha channel, handles palette modes)
    if image.mode != "RGB":
        # Если есть прозрачность или палитра, приводим к RGBA для безопасного наложения
        if image.mode in ("RGBA", "LA", "P") or "transparency" in image.info:
            if image.mode != "RGBA":
                image = image.convert("RGBA")

            # Создаем белый фон и накладываем изображение через альфа-канал
            background = Image.new("RGB", image.size, (255, 255, 255))
            background.paste(
                image, mask=image.split()[-1]
            )  # Последний канал всегда альфа в RGBA
            image = background
        else:
            # Для режимов вроде L (grayscale), CMYK, YCbCr
            image = image.convert("RGB")

    return image


def generate_thumbnail(
    image: Image.Image, size: tuple[int, int], quality: int
) -> bytes:
    """Generate a square WebP thumbnail with center crop.

    Args:
        image: PIL Image in RGB mode
        size: Target size (width, height) - should be square
        quality: WebP quality (1-100)

    Returns:
        WebP image bytes
    """
    # Center crop to square
    width, height = image.size
    if width != height:
        # Calculate crop box for center crop
        min_dim = min(width, height)
        left = (width - min_dim) // 2
        top = (height - min_dim) // 2
        right = left + min_dim
        bottom = top + min_dim
        image = image.crop((left, top, right, bottom))

    # Resize to target size using high-quality resampling
    image = image.resize(size, Image.Resampling.LANCZOS)

    # Save as WebP
    output = io.BytesIO()
    image.save(output, format="WEBP", quality=quality, method=6)
    return output.getvalue()
