from sqlalchemy import ForeignKey, String, UniqueConstraint, DateTime # <-- Add DateTime
from sqlalchemy.sql import func # <-- Add func
from datetime import datetime # <-- Add datetime
from sqlalchemy.orm import Mapped, mapped_column
from ..db.base import Base
import uuid

class Membership(Base):
    __tablename__ = "memberships"
    __table_args__ = (
        # Enforce one membership per user (prevents multi-org for same email)
        UniqueConstraint("user_id", name="uq_membership_user_single_org"),
    )

    id: Mapped[uuid.UUID] = mapped_column(default=uuid.uuid4, primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(10), nullable=False, server_default="user")  # 'admin' or 'user'
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
