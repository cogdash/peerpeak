"""Shared dependencies and utilities."""

import os
from pathlib import Path
from fastapi import Depends
from fastapi.templating import Jinja2Templates

from core.storage import S3Storage, storage

BASE_DIR = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
templates = Jinja2Templates(directory=TEMPLATES_DIR)


def get_storage() -> S3Storage:
    """Get the S3Storage instance."""
    return storage
