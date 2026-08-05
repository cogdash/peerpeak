import os
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

# Read from environment (Docker Compose sets this), fallback to local dev
DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql+psycopg2://postgres:postgres@localhost:5432/peerpeak"
)

engine = create_engine(DATABASE_URL)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()
