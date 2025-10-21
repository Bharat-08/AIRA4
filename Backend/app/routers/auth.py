# recruiter-platform/backend/app/routers/auth.py

from fastapi import APIRouter, Depends, Request, Response, HTTPException
from starlette.responses import RedirectResponse
from sqlalchemy.orm import Session

from ..db.session import get_db
from ..services.auth import oauth, provision_via_invite
from ..security.jwt import issue_jwt, set_jwt_cookie, clear_jwt_cookie
from ..config import settings

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.get("/google/login")
async def google_login(request: Request):
    """
    Kicks off the Google OAuth flow by redirecting the user to Google.
    """
    redirect_uri = str(request.url_for("google_callback"))
    return await oauth.google.authorize_redirect(request, redirect_uri)


@router.get("/google/callback")
async def google_callback(request: Request, db: Session = Depends(get_db)):
    """
    Handles the callback from Google after the user has authenticated.
    """
    token = await oauth.google.authorize_access_token(request)
    user_info = token.get('userinfo')
    if not user_info:
        raise HTTPException(status_code=400, detail="Could not retrieve user info from Google.")

    email = user_info.get("email")
    if not email:
        raise HTTPException(status_code=400, detail="Google profile is missing an email address.")

    # --- THIS SECTION IS CORRECTED ---
    # 1. Get the name and avatar URL from the Google profile.
    name = user_info.get("name")
    avatar_url = user_info.get("picture")

    # 2. Pass all required arguments to the provisioning function.
    user, org, membership = provision_via_invite(
        db,
        email=email,
        name=name,
        avatar_url=avatar_url
    )
    # --- END OF CORRECTION ---

    access_token = issue_jwt(
        sub=str(user.id),
        org_id=str(membership.org_id),
        role=membership.role
    )
    
    # Corrected: Changed to point directly to your landing page
    redirect_url = f"{settings.FRONTEND_BASE_URL}/RecruiterDashboardPage"
    response = RedirectResponse(url=redirect_url)
    set_jwt_cookie(response, access_token)
    return response


@router.post("/logout")
def logout():
    """
    Logs the user out by clearing their session cookie.
    """
    response = Response(status_code=204)
    clear_jwt_cookie(response)
    return response
