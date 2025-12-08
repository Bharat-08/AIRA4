# backend/app/db/session.py
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session
from app.config import settings

# Create the SQLAlchemy engine using your DATABASE_URL
# UPDATED: Strict pool settings for shared development database
engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    # Keep this LOW. 10 devs * 2 connections = 20 connections.
    # Supabase free tier limit is ~60.
    pool_size=2,
    # Allow small bursts only
    max_overflow=1,
    pool_recycle=1800
)

# Create a thread-safe, configured "Session" class
SessionLocal = scoped_session(
    sessionmaker(autocommit=False, autoflush=False, bind=engine)
)

# The dependency function to provide a database session per request
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()