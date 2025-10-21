from __future__ import annotations
from sqlalchemy import DateTime, String, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from ..db.base import Base
from datetime import datetime
from typing import List
import uuid # <-- THIS LINE IS THE FIX

class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(120), unique=True, index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(20), server_default="active", nullable=False)

    # This is the correct relationship. An Organization has many Users.
    users: Mapped[List["User"]] = relationship(back_populates="organization")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

