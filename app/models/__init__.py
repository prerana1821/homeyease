"""Database models for the meal planning bot."""
from app.models.database import Base, engine
from app.models.user import User
from app.models.meal import Meal
from app.models.user_pantry import UserPantry
from app.models.session import Session
from app.models.meal_plan import MealPlan

# Create all tables
try:
    Base.metadata.create_all(bind=engine)
    print("Database tables created successfully")
except Exception as e:
    print(f"Error creating database tables: {e}")
    
# Export all models
__all__ = ["User", "Meal", "UserPantry", "Session", "MealPlan", "Base", "engine"]