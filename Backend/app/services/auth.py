import hashlib
import uuid
from datetime import datetime, timezone
from authlib.integrations.starlette_client import OAuth
from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import select, func

from ..config import settings
from ..models.user import User
from ..models.organization import Organization
from ..models.membership import Membership
from ..models.invitation import Invitation

oauth = OAuth()
oauth.register(
    name="google",
    client_id=settings.GOOGLE_CLIENT_ID,
    client_secret=settings.GOOGLE_CLIENT_SECRET,
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_kwargs={"scope": "openid email profile"},
)

def upsert_user(db: Session, *, email: str, name: str | None, avatar_url: str | None) -> User:
    """
    Creates a new user or updates an existing one with the latest login time and details.
    """
    user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    now = datetime.now(timezone.utc)

    if user is None:
        user = User(
            id=uuid.uuid4(),
            email=email,
            name=name,
            avatar_url=avatar_url,
            last_login_at=now,
        )
        db.add(user)
    else:
        if name: user.name = name
        if avatar_url: user.avatar_url = avatar_url
        user.last_login_at = now

    db.flush()
    return user

def provision_via_invite(db: Session, email: str, name: str | None, avatar_url: str | None):
    """
    Handles user provisioning for both new and returning users.
    1. Checks if a user already exists and has a membership.
    2. If not, validates their invitation and creates the user and membership.
    """
    # --- vvv START: BUG FIX LOGIC vvv ---

    # 1. Check if the user already exists and has a membership.
    existing_user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if existing_user:
        membership = db.execute(select(Membership).where(Membership.user_id == existing_user.id)).scalar_one_or_none()
        if membership:
            # This is a returning user. Update their details and log them in.
            user = upsert_user(db, email=email, name=name, avatar_url=avatar_url)
            organization = db.get(Organization, membership.org_id)
            db.commit()
            return user, organization, membership

    # --- ^^^ END: BUG FIX LOGIC ^^^ ---

    # 2. If user is new or has no membership, they MUST have a valid invite.
    invitation = db.execute(
        select(Invitation).where(
            Invitation.email == email,
            Invitation.accepted_at.is_(None),
            Invitation.expires_at > func.now(),
        )
    ).scalar_one_or_none()

    if not invitation:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No valid invitation found. Contact your admin.")

    try:
        # Create or update the user record
        user = upsert_user(db, email=email, name=name, avatar_url=avatar_url)

        # Create the membership
        new_membership = Membership(user_id=user.id, org_id=invitation.org_id, role=invitation.role)
        db.add(new_membership)

        # Mark the invitation as accepted
        invitation.accepted_at = func.now()

        organization = db.get(Organization, invitation.org_id)

        # Commit all changes at once
        db.commit()
        db.refresh(new_membership)
        
        return user, organization, new_membership

    except Exception:
        db.rollback()
        raise
