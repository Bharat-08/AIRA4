# In backend/app/models/favorite.py

import uuid
from datetime import datetime
from sqlalchemy import ForeignKey, String, DateTime, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base

class Favorite(Base):
    __tablename__ = "favorites"

    id: Mapped[uuid.UUID] = mapped_column(default=uuid.uuid4, primary_key=True)
    
    # Who favorited the candidate
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"))

    # We need a way to identify the job this favorite belongs to.
    # For now, we'll use a simple string, but this could be a ForeignKey later.
    job_id: Mapped[str] = mapped_column(String(255), index=True)

    # A unique identifier for the candidate (e.g., their LinkedIn URL or an internal ID)
    candidate_id: Mapped[str] = mapped_column(String(512), index=True)

    # Store all the detailed ranking data as a flexible JSON object
    ranking_data: Mapped[dict] = mapped_column(JSONB)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())