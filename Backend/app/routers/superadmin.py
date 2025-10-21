# In backend/app/routers/superadmin.py

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr

from app.db.session import get_db
from app.security.deps import require_superadmin
from app.models.organization import Organization
from app.models.invitation import Invitation
from app.services.invitations import create_invitation_token # We will create this service next

router = APIRouter()

# Pydantic model for the request body
class OrgInvitationRequest(BaseModel):
    org_name: str
    admin_email: EmailStr

@router.post("/invite-organization", status_code=status.HTTP_201_CREATED)
def invite_organization(
    invite_data: OrgInvitationRequest,
    db: Session = Depends(get_db),
    current_user_ctx: dict = Depends(require_superadmin)
):
    """
    Super Admin endpoint to create a new organization and invite its first admin.
    """
    # 1. Check if an organization with that name already exists
    existing_org = db.query(Organization).filter(Organization.name == invite_data.org_name).first()
    if existing_org:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Organization '{invite_data.org_name}' already exists."
        )

    # 2. Create the new organization
    new_org = Organization(
        name=invite_data.org_name,
        # We can create a simple 'slug' from the name for URLs
        slug=invite_data.org_name.lower().replace(" ", "-")
    )
    db.add(new_org)
    db.commit()
    db.refresh(new_org)

    # 3. Create an invitation for the new organization's admin
    # This assumes create_invitation_token is a service we'll build next.
    # For now, we can use a placeholder.
    token_hashed, expires_at = create_invitation_token()

    invitation = Invitation(
        org_id=new_org.id,
        email=invite_data.admin_email,
        role="admin", # The first user of an org is always an admin
        invited_by=current_user_ctx["user"].id,
        token_hashed=token_hashed,
        expires_at=expires_at
    )
    db.add(invitation)
    db.commit()

    return {
        "message": "Organization created and invitation sent successfully.",
        "org_id": str(new_org.id),
        "invitation_email": invitation.email
    }