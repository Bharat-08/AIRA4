# In backend/app/services/invitations.py

import os
import hashlib
from datetime import datetime, timedelta, timezone

def create_invitation_token():
    """
    Generates a secure random token, its hash, and an expiration time.

    Returns:
        tuple: A tuple containing the hashed token (str) and the expiration datetime.
    """
    # 1. Generate a secure, random token
    # We generate 32 random bytes and convert them to a URL-safe hex string.
    # This raw token will be sent to the user's email.
    raw_token = os.urandom(32).hex()

    # 2. Hash the token for database storage
    # We never store the raw token in the database for security.
    # We store its hash and compare against it when the user clicks the link.
    token_hashed = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()

    # 3. Set an expiration time (e.g., 7 days from now)
    expires_at = datetime.now(timezone.utc) + timedelta(days=7)

    # Note: We are only returning the hashed token and expiration date.
    # The raw_token would be returned here as well to be sent in an email.
    # For now, since we don't have email sending set up, we just return
    # what's needed for the database.
    return token_hashed, expires_at