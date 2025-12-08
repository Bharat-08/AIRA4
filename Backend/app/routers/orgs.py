from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.db.session import get_db
from app.security.deps import require_admin, get_current_user  # ✅ Added get_current_user
from app.models.invitation import Invitation
from app.models.user import User
from app.models.membership import Membership
from app.services.invitations import create_invitation_token

router = APIRouter(prefix="/orgs", tags=["Organizations"])

# Pydantic model for the invitation request body
class UserInvitationRequest(BaseModel):
    email: EmailStr
    role: str = "user"

@router.post("/invitations", status_code=status.HTTP_201_CREATED)
def invite_user_to_org(
    invite_data: UserInvitationRequest,
    db: Session = Depends(get_db),
    ctx: dict = Depends(require_admin)
):
    """
    Organization Admin endpoint to invite a new user to their organization.
    """
    admin_user = ctx["user"]
    admin_membership = ctx["membership"]

    # Block inviting an email that already belongs to a *different* org
    existing_member = db.execute(
        select(Membership).join(User).where(User.email == str(invite_data.email))
    ).scalar_one_or_none()

    if existing_member and existing_member.org_id != admin_membership.org_id:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already belongs to another organization.")

    # Check if an invitation for this email already exists for this org
    existing_invitation = db.query(Invitation).filter(
        Invitation.email == invite_data.email,
        Invitation.org_id == admin_membership.org_id
    ).first()

    if existing_invitation:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="An invitation for this email address already exists for this organization."
        )

    # Generate a new token for the invitation using our service
    token_hashed, expires_at = create_invitation_token()

    # Create the new invitation record
    new_invitation = Invitation(
        org_id=admin_membership.org_id,
        email=str(invite_data.email).lower(),
        role=invite_data.role,
        invited_by=admin_user.id,
        token_hashed=token_hashed,
        expires_at=expires_at
    )

    db.add(new_invitation)
    db.commit()

    return {
        "message": "Invitation sent successfully.",
        "invitation": {
            "email": new_invitation.email,
            "role": new_invitation.role,
            "org_id": str(new_invitation.org_id)
        }
    }

@router.get("/invitations")
def list_invitations(ctx=Depends(require_admin), db: Session = Depends(get_db)):
    """
    Lists all pending and accepted invitations for the admin's organization.
    """
    invitations = db.execute(
        select(Invitation)
        .where(Invitation.org_id == ctx["membership"].org_id)
        .order_by(Invitation.created_at.desc())
    ).scalars().all()
    
    return [
        {
            "id": str(inv.id),
            "email": inv.email,
            "role": inv.role,
            "expires_at": inv.expires_at,
            "accepted_at": inv.accepted_at
        } for inv in invitations
    ]

@router.get("/users")
def list_org_users(ctx=Depends(require_admin), db: Session = Depends(get_db)):
    """
    Lists all users who are members of the admin's organization.
    """
    members = db.execute(
        select(User, Membership)
        .join(Membership, Membership.user_id == User.id)
        .where(Membership.org_id == ctx["membership"].org_id)
    ).all()

    return [
        {
            "id": str(user.id),
            "email": user.email,
            "name": user.name,
            "role": membership.role
        } for user, membership in members
    ]

# ✅ NEW ENDPOINT: Get Teammates (for regular users)
@router.get("/teammates")
def get_teammates(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Fetches other users in the same organization as the current user.
    Used for recommending candidates to teammates.
    """
    if not current_user.organization_id:
        return []

    # Fetch users with same org_id, excluding the current user
    teammates = db.execute(
        select(User)
        .where(User.organization_id == current_user.organization_id)
        .where(User.id != current_user.id)
    ).scalars().all()

    return [
        {
            "id": str(t.id),
            "name": t.name,
            "email": t.email,
            "avatar_url": t.avatar_url
        } for t in teammates
    ]