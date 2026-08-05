"""Short unique ID generation utilities."""

import uuid
import base64
import time
import random
import string


def generate_short_id(length: int = 12) -> str:
    """
    Generate a short unique ID using base62 encoding of UUID.

    Args:
        length: Length of the ID (default 12 characters)

    Returns:
        A short unique ID string
    """
    # Generate a UUID and encode it in base62
    uuid_bytes = uuid.uuid4().bytes
    # Use base64 url-safe encoding and remove padding
    b64 = base64.urlsafe_b64encode(uuid_bytes).decode("ascii").rstrip("=")
    # Convert to base62 (alphanumeric only)
    return b64[:length]


def generate_nanoid(length: int = 12) -> str:
    """
    Generate a nanoid-like short unique ID.

    Args:
        length: Length of the ID (default 12 characters)

    Returns:
        A short unique ID string using alphanumeric characters
    """
    alphabet = string.ascii_letters + string.digits
    return "".join(random.choices(alphabet, k=length))


def generate_timestamp_id(length: int = 10) -> str:
    """
    Generate a short ID based on timestamp + random component.

    Args:
        length: Length of the random component (default 10)

    Returns:
        A short unique ID string
    """
    timestamp = int(time.time() * 1000)  # milliseconds
    timestamp_b62 = base62_encode(timestamp)
    random_part = generate_nanoid(length)
    return f"{timestamp_b62}{random_part}"


def base62_encode(num: int) -> str:
    """Encode a number in base62."""
    alphabet = string.digits + string.ascii_lowercase + string.ascii_uppercase
    if num == 0:
        return alphabet[0]
    result = []
    while num > 0:
        num, rem = divmod(num, 62)
        result.append(alphabet[rem])
    return "".join(reversed(result))


# Default ID generator - using nanoid for simplicity and good collision resistance
generate_id = generate_nanoid
