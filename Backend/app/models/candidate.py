# backend/app/models/candidate.py
import uuid
from datetime import datetime
from sqlalchemy import (
    String,
    DateTime,
    Text,
    ForeignKey,
    UUID,
    Integer,
    Boolean,
    Numeric,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func, expression
from ..db.base import Base


class RankedCandidate(Base):
    __tablename__ = "ranked_candidates"

    rank_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE")
    )
    jd_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jds.jd_id", ondelete="CASCADE")
    )
    profile_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    rank: Mapped[int] = mapped_column(Integer, nullable=True)
    match_score: Mapped[float] = mapped_column(Numeric(5, 2), nullable=True)
    strengths: Mapped[str] = mapped_column(Text, nullable=True)
    # Use server_default expression.false() and make column non-nullable
    favorite: Mapped[bool] = mapped_column(Boolean, server_default=expression.false(), nullable=False)
    save_for_future: Mapped[bool] = mapped_column(Boolean, server_default=expression.false(), nullable=False)
    send_to_recruiter: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    outreached: Mapped[bool] = mapped_column(Boolean, server_default=expression.false(), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), server_default=func.now()
    )
    linkedin_url: Mapped[str] = mapped_column(Text, nullable=True)

    # --- NEW COLUMNS ---
    contacted: Mapped[bool] = mapped_column(Boolean, server_default=expression.false(), nullable=False)
    stage: Mapped[str] = mapped_column(String, server_default="In Consideration", nullable=False)
    
    # ✅ NEW: Recommended to Role Flag
    is_recommended: Mapped[bool] = mapped_column(Boolean, server_default=expression.false(), nullable=False)
    # --- END NEW COLUMNS ---

    # Relationships
    user = relationship("User", foreign_keys=[user_id])
    recruiter = relationship("User", foreign_keys=[send_to_recruiter])
    jd = relationship("JD")


class RankedCandidateFromResume(Base):
    __tablename__ = "ranked_candidates_from_resume"

    rank_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE")
    )
    jd_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jds.jd_id", ondelete="CASCADE")
    )
    resume_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    rank: Mapped[int] = mapped_column(Integer, nullable=True)
    match_score: Mapped[float] = mapped_column(Numeric(5, 2), nullable=True)
    strengths: Mapped[str] = mapped_column(Text, nullable=True)
    # Use server_default expression.false() and make column non-nullable
    favorite: Mapped[bool] = mapped_column(Boolean, server_default=expression.false(), nullable=False)
    save_for_future: Mapped[bool] = mapped_column(Boolean, server_default=expression.false(), nullable=False)
    send_to_recruiter: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    outreached: Mapped[bool] = mapped_column(Boolean, server_default=expression.false(), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), server_default=func.now()
    )
    linkedin_url: Mapped[str] = mapped_column(Text, nullable=True)

    # --- NEW COLUMNS ---
    contacted: Mapped[bool] = mapped_column(Boolean, server_default=expression.false(), nullable=False)
    stage: Mapped[str] = mapped_column(String, server_default="In Consideration", nullable=False)

    # ✅ NEW: Recommended to Role Flag
    is_recommended: Mapped[bool] = mapped_column(Boolean, server_default=expression.false(), nullable=False)
    # --- END NEW COLUMNS ---

    # Relationships
    user = relationship("User", foreign_keys=[user_id])
    recruiter = relationship("User", foreign_keys=[send_to_recruiter])
    jd = relationship("JD")