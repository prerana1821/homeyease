"""Database models for the meal planning bot."""
from app.models.database import Base, engine
from app.models.user import User
from app.models.meal import Meal

# Create all tables
Base.metadata.create_all(bind=engine)