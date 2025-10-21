# In backend/app/db/base.py

from sqlalchemy.orm import DeclarativeBase

# This is the base class which all your models will inherit.
class Base(DeclarativeBase):
    pass