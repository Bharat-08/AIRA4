# recruiter-platform/backend/app/models/user.py

from __future__ import annotations
from sqlalchemy import String, DateTime, Boolean, ForeignKey, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from ..db.base import Base
import uuid
from datetime import datetime
from typing import List

class User(Base):
    __tablename__ = "users"

    # --- Base Columns ---
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    is_superadmin: Mapped[bool] = mapped_column(default=False, nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # --- CORRECTED: Relationship to Organization ---
    # The foreign key is now correctly typed as UUID to match the Organization's primary key.
    organization_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("organizations.id"), nullable=True)
    organization: Mapped["Organization"] = relationship(back_populates="users")

    # --- Relationship to JDs ---
    # This creates the one-to-many relationship from a User to their submitted JDs.
    jds: Mapped[List["JD"]] = relationship(back_populates="user")

