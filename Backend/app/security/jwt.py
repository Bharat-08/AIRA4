# recruiter-platform/backend/app/security/jwt.py

import jwt
from datetime import datetime, timedelta, timezone
from fastapi import Response, HTTPException, status
from ..config import settings

ALGO = "RS256"

def issue_jwt(sub: str, org_id: str, role: str) -> str:
    """
    Creates a new JWT for a user session.
    """
    now = datetime.now(timezone.utc)
    payload = {
        "iat": now,
        "exp": now + timedelta(minutes=settings.JWT_EXPIRATION_MINUTES),
        "sub": sub,
        "org_id": org_id,
        "role": role,
    }
    private_key_bytes = settings.JWT_PRIVATE_KEY.encode('utf-8')
    
    # ----> ADD THIS DEBUG CODE <----
    print("--- DEBUG: JWT_PRIVATE_KEY as read by settings ---")
    print(repr(settings.JWT_PRIVATE_KEY))
    print("--- END DEBUG ---")
    # ---------------------------------
    
    # ----> ADD THIS NEW DEBUG CODE <----
    print("--- DEBUG: JWT_PUBLIC_KEY as read by settings ---")
    print(repr(settings.JWT_PUBLIC_KEY))
    print("--- END DEBUG ---")
    # ---------------------
    
    token = jwt.encode(payload, private_key_bytes, algorithm=ALGO)
    return token

def set_jwt_cookie(response: Response, token: str):
    """
    Sets the JWT as a secure, httpOnly cookie on the response.
    """
    response.set_cookie(
        key=settings.COOKIE_NAME,
        value=token,
        httponly=True,
        secure=True if settings.APP_ENV != "dev" else False,
        samesite="lax",
        max_age=settings.JWT_EXPIRATION_MINUTES * 60
    )

def clear_jwt_cookie(response: Response):
    """
    Clears the JWT cookie from the response.
    """
    response.delete_cookie(key=settings.COOKIE_NAME)

def verify_jwt(token: str) -> dict:
    """
    Verifies a JWT and returns its payload.
    Raises HTTPException if the token is invalid.
    """
    try:
        public_key_bytes = settings.JWT_PUBLIC_KEY.encode('utf-8')
        payload = jwt.decode(token, public_key_bytes, algorithms=[ALGO])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token has expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
