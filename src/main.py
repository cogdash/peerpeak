import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from core.database import engine
from core.auth import get_db, SESSION_EXPIRY_DAYS
from models import Base
from routers import auth_router, profile_router, feed_router, avatar_router

# Create tables
Base.metadata.create_all(bind=engine)

app = FastAPI()

BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
templates = Jinja2Templates(directory=TEMPLATES_DIR)

# Mount static files
STATIC_DIR = os.path.join(BASE_DIR, "static")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# Include routers
app.include_router(auth_router)
app.include_router(profile_router)
app.include_router(feed_router)
app.include_router(avatar_router)
