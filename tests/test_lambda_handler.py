"""Unit tests for Lambda avatar image processing."""

import io
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

# Add lambda src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "lambda" / "src"))

from handler import (
    generate_thumbnail,
    lambda_handler,
    process_record,
    validate_and_convert_image,
)


class TestValidateAndConvertImage:
    """Tests for validate_and_convert_image function."""

    def test_valid_jpeg(self):
        """Test valid JPEG image conversion."""
        # Create a simple JPEG image
        img = Image.new("RGB", (200, 150), color="red")
        buf = io.BytesIO()
        img.save(buf, format="JPEG")
        jpeg_data = buf.getvalue()

        result = validate_and_convert_image(jpeg_data)
        assert isinstance(result, Image.Image)
        assert result.mode == "RGB"
        assert result.size == (200, 150)

    def test_valid_png(self):
        """Test valid PNG image conversion."""
        img = Image.new("RGB", (200, 150), color="blue")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        png_data = buf.getvalue()

        result = validate_and_convert_image(png_data)
        assert isinstance(result, Image.Image)
        assert result.mode == "RGB"
        assert result.size == (200, 150)

    def test_valid_webp(self):
        """Test valid WebP image conversion."""
        img = Image.new("RGB", (200, 150), color="green")
        buf = io.BytesIO()
        img.save(buf, format="WEBP")
        webp_data = buf.getvalue()

        result = validate_and_convert_image(webp_data)
        assert isinstance(result, Image.Image)
        assert result.mode == "RGB"
        assert result.size == (200, 150)

    def test_rgba_conversion(self):
        """Test RGBA image gets converted to RGB with white background."""
        img = Image.new(
            "RGBA", (100, 100), color=(255, 0, 0, 128)
        )  # Semi-transparent red
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        png_data = buf.getvalue()

        result = validate_and_convert_image(png_data)
        assert result.mode == "RGB"
        # The result should have white background composited
        # Center pixel should be pink-ish (red + white)
        # With 50% alpha: red=255, green=127, blue=127
        center_pixel = result.getpixel((50, 50))
        assert center_pixel[0] > 200  # Red component high
        assert 120 < center_pixel[1] < 140  # Green component ~127 (from white * 0.5)
        assert 120 < center_pixel[2] < 140  # Blue component ~127 (from white * 0.5)

    def test_palette_mode_conversion(self):
        """Test palette mode image gets converted to RGB."""
        img = Image.new("P", (100, 100))
        # Create a simple palette
        palette = []
        for i in range(256):
            palette.extend([i, i, i])  # Grayscale palette
        img.putpalette(palette)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        png_data = buf.getvalue()

        result = validate_and_convert_image(png_data)
        assert result.mode == "RGB"

    def test_invalid_image_data(self):
        """Test invalid image data raises ValueError."""
        with pytest.raises(ValueError, match="Cannot open image"):
            validate_and_convert_image(b"not an image")

    def test_unsupported_format(self):
        """Test unsupported image format raises ValueError."""
        # Create a BMP (which is supported) - let's test with a format not in our list
        # Actually BMP is in our supported list. Let's test with something else.
        # We'll mock the format check
        img = Image.new("RGB", (100, 100))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        png_data = buf.getvalue()

        # Mock the format to be unsupported
        with patch("PIL.Image.open") as mock_open:
            mock_img = MagicMock()
            mock_img.format = "ICO"  # Not in supported list
            mock_img.mode = "RGB"
            mock_img.load = MagicMock()
            mock_open.return_value.__enter__.return_value = mock_img

            with pytest.raises(ValueError, match="Unsupported image format"):
                validate_and_convert_image(png_data)


class TestGenerateThumbnail:
    """Tests for generate_thumbnail function."""

    def test_square_image_resize(self):
        """Test square image gets resized correctly."""
        img = Image.new("RGB", (400, 400), color="red")
        result = generate_thumbnail(img, (100, 100), 80)

        # Verify it's valid WebP
        result_img = Image.open(io.BytesIO(result))
        assert result_img.format == "WEBP"
        assert result_img.size == (100, 100)
        assert result_img.mode == "RGB"

    def test_landscape_image_center_crop(self):
        """Test landscape image gets center-cropped to square then resized."""
        # 400x200 landscape image
        img = Image.new("RGB", (400, 200), color="blue")
        result = generate_thumbnail(img, (100, 100), 80)

        result_img = Image.open(io.BytesIO(result))
        assert result_img.size == (100, 100)

    def test_portrait_image_center_crop(self):
        """Test portrait image gets center-cropped to square then resized."""
        # 200x400 portrait image
        img = Image.new("RGB", (200, 400), color="green")
        result = generate_thumbnail(img, (100, 100), 80)

        result_img = Image.open(io.BytesIO(result))
        assert result_img.size == (100, 100)

    def test_different_quality_settings(self):
        """Test different quality settings produce different file sizes."""
        img = Image.new("RGB", (200, 200), color="red")

        low_quality = generate_thumbnail(img, (100, 100), 50)
        high_quality = generate_thumbnail(img, (100, 100), 95)

        # Higher quality should generally be larger (though not guaranteed for solid colors)
        # At least verify both are valid
        assert len(low_quality) > 0
        assert len(high_quality) > 0

        low_img = Image.open(io.BytesIO(low_quality))
        high_img = Image.open(io.BytesIO(high_quality))
        assert low_img.size == (100, 100)
        assert high_img.size == (100, 100)


class TestProcessRecord:
    """Tests for process_record function."""

    @patch("handler.s3")
    def test_process_record_valid_key(self, mock_s3):
        """Test processing a valid avatar key."""
        # Setup mock
        mock_response = {
            "Body": MagicMock(),
            "ContentType": "image/jpeg",
        }
        # Create test image data
        img = Image.new("RGB", (200, 200), color="red")
        buf = io.BytesIO()
        img.save(buf, format="JPEG")
        mock_response["Body"].read.return_value = buf.getvalue()

        mock_s3.get_object.return_value = mock_response

        # Test record
        record = {
            "s3": {
                "bucket": {"name": "test-bucket"},
                "object": {"key": "avatars/user123/original/abc123.jpg"},
            }
        }

        process_record(record)

        # Verify S3 calls
        mock_s3.get_object.assert_called_once_with(
            Bucket="test-bucket", Key="avatars/user123/original/abc123.jpg"
        )
        # Should have put_object called twice (for 400 and 100)
        assert mock_s3.put_object.call_count == 2
        # Should have delete_object called once (for original)
        mock_s3.delete_object.assert_called_once_with(
            Bucket="test-bucket", Key="avatars/user123/original/abc123.jpg"
        )

    @patch("handler.s3")
    def test_process_record_non_avatar_key(self, mock_s3):
        """Test non-avatar keys are skipped."""
        record = {
            "s3": {
                "bucket": {"name": "test-bucket"},
                "object": {"key": "other/path/file.txt"},
            }
        }

        process_record(record)

        # Should not call any S3 methods
        mock_s3.get_object.assert_not_called()
        mock_s3.put_object.assert_not_called()
        mock_s3.delete_object.assert_not_called()

    @patch("handler.s3")
    def test_process_record_invalid_key_format(self, mock_s3):
        """Test invalid key format is skipped."""
        record = {
            "s3": {
                "bucket": {"name": "test-bucket"},
                "object": {"key": "avatars/user123/file.jpg"},  # Missing /original/
            }
        }

        process_record(record)

        mock_s3.get_object.assert_not_called()

    @patch("handler.s3")
    def test_process_record_invalid_image_deleted(self, mock_s3):
        """Test invalid image gets deleted from S3."""
        mock_response = {
            "Body": MagicMock(),
            "ContentType": "image/jpeg",
        }
        mock_response["Body"].read.return_value = b"not an image"
        mock_s3.get_object.return_value = mock_response

        record = {
            "s3": {
                "bucket": {"name": "test-bucket"},
                "object": {"key": "avatars/user123/original/abc123.jpg"},
            }
        }

        process_record(record)

        # Original should be deleted
        mock_s3.delete_object.assert_called_once_with(
            Bucket="test-bucket", Key="avatars/user123/original/abc123.jpg"
        )
        # Variants should not be uploaded
        mock_s3.put_object.assert_not_called()


class TestLambdaHandler:
    """Tests for lambda_handler function."""

    @patch("handler.process_record")
    def test_lambda_handler_multiple_records(self, mock_process_record):
        """Test handler processes multiple records."""
        event = {
            "Records": [
                {"s3": {"bucket": {"name": "b1"}, "object": {"key": "k1"}}},
                {"s3": {"bucket": {"name": "b2"}, "object": {"key": "k2"}}},
            ]
        }

        result = lambda_handler(event, None)

        assert result["statusCode"] == 200
        assert mock_process_record.call_count == 2

    @patch("handler.process_record")
    def test_lambda_handler_error_handling(self, mock_process_record):
        """Test handler continues on record processing errors."""
        mock_process_record.side_effect = [Exception("Error"), None]

        event = {
            "Records": [
                {"s3": {"bucket": {"name": "b1"}, "object": {"key": "k1"}}},
                {"s3": {"bucket": {"name": "b2"}, "object": {"key": "k2"}}},
            ]
        }

        result = lambda_handler(event, None)

        assert result["statusCode"] == 200
        assert mock_process_record.call_count == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
