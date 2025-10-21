# backend/app/db/session.py
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session
from app.config import settings

# Create the SQLAlchemy engine using your DATABASE_URL
engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
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