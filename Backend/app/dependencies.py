# backend/app/dependencies.py

from fastapi import Depends, HTTPException, status, Request
from supabase import Client
from jose import JWTError, jwt
from typing import Optional
from sqlalchemy.orm import Session

from .config import settings
from .supabase import supabase_client
from .models.user import User
# --- MODIFICATION: Import SessionLocal to create DB sessions ---
from .db.session import SessionLocal

# --- NEW FUNCTION: The missing get_db dependency ---
def get_db():
    """Dependency to get a SQLAlchemy database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
# ----------------------------------------------------

def get_supabase_client() -> Client:
    """Dependency to get the Supabase client instance."""
    return supabase_client

async def get_current_user(
    request: Request, 
    db: Session = Depends(get_db) # MODIFIED: Use the new get_db dependency
) -> User:
    """
    Dependency to get the current user.
    
    Reads the JWT from the access_token cookie, verifies its signature and
    expiration, then fetches the corresponding user from the database.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    try:
        token = request.cookies.get(settings.COOKIE_NAME)
        if token is None:
            raise credentials_exception

        # Decode the JWT using the public key and the algorithm from settings
        payload = jwt.decode(
            token, 
            settings.JWT_PUBLIC_KEY, 
            algorithms=[settings.JWT_ALGORITHM]
        )
        
        # 'sub' (subject) is the standard claim for the user's unique ID
        user_id: Optional[str] = payload.get("sub")
        if user_id is None:
            raise credentials_exception

    except JWTError:
        # This will catch any error during decoding (e.g., invalid signature, expired token)
        raise credentials_exception

    # --- MODIFICATION: Fetch user from PostgreSQL via SQLAlchemy session ---
    user = db.query(User).filter(User.id == user_id).first()

    if not user:
         raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    return user
