# backend/app/models/jd.py

from __future__ import annotations
import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, Text, ForeignKey, UUID, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from ..db.base import Base

class JD(Base):
    __tablename__ = "jds"

    # Columns based on your provided schema
    jd_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # --- MISSING COLUMNS ADDED ---
    # These are required by your JdSummary schema but were missing from the model
    role: Mapped[str | None] = mapped_column(Text, nullable=True)
    key_requirements: Mapped[str | None] = mapped_column(Text, nullable=True)
    # -----------------------------

    file_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    location: Mapped[str | None] = mapped_column(Text, nullable=True)
    job_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    experience_required: Mapped[str | None] = mapped_column(Text, nullable=True)
    jd_parsed_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    
    # --- NEW COLUMN: Stores the original, complete JD content ---
    jd_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    # --- FIX: Added status column ---
    # This allows SQLAlchemy to filter by status="Open"
    status: Mapped[str | None] = mapped_column(String, default="Open", nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    
    # --- EXISTING COLUMNS: For sorting and stats ---
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    candidates_liked: Mapped[int] = mapped_column(Integer, default=0)
    candidates_contacted: Mapped[int] = mapped_column(Integer, default=0)

    # Foreign Key to the User who uploaded it
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    
    # Relationship to the User model
    user: Mapped["User"] = relationship(back_populates="jds")