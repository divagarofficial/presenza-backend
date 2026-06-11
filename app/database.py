#prazenza-backend/app/database.py
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
import os

# Local dev: SQLite file in this folder if DATABASE_URL is not set.
# Production: set DATABASE_URL (e.g. postgresql+psycopg2://user:pass@host/db).
DATABASE_URL = os.getenv("DATABASE_URL") or "sqlite:///./presenza.db"

_engine_kwargs = {
    "echo": True,
    "pool_pre_ping": True,
    "pool_recycle": 300,
}
if DATABASE_URL.startswith("sqlite"):
    _engine_kwargs["connect_args"] = {"check_same_thread": False}

engine = create_engine(DATABASE_URL, **_engine_kwargs)


SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)

Base = declarative_base()
