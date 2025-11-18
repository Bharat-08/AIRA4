# Backend/app/models/linkedin.py
import uuid
from datetime import datetime
from sqlalchemy import (
    Text,
    DateTime,
    ForeignKey,
    UUID,
    Boolean,  # <-- Import this
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from ..db.base import Base


class LinkedIn(Base):
    """
    SQLAlchemy model mapping to public.linkedin.

    Note:
      - The DB default uses gen_random_uuid(); here we use uuid.uuid4() on the app side.
      - created_at in the table is "timestamp without time zone", so timezone=False.
    """
    __tablename__ = "linkedin"

    linkedin_profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    jd_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jds.jd_id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    # Profile fields
    name: Mapped[str | None] = mapped_column(Text, nullable=True)
    profile_link: Mapped[str | None] = mapped_column(Text, nullable=True)
    position: Mapped[str | None] = mapped_column(Text, nullable=True)
    company: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), server_default=func.now(), nullable=False
    )

    # --- ADD THESE TWO COLUMNS ---
    save_for_future: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    favourite: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    # ---------------------------

    # Relationships (optional convenience)
    user = relationship("User", foreign_keys=[user_id])
    jd = relationship("JD", foreign_keys=[jd_id])