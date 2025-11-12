# backend/app/models/__init__.py

# This file imports all the models, making them available
# to the SQLAlchemy Base and resolving circular dependencies.

from .user import User
from .organization import Organization
from .jd import JD

# Add any other models you have here, for example:
# from .membership import Membership
# from .invitation import Invitation
# from .favorite import Favorite
