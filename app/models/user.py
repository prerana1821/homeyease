"""
User model for storing user profiles and preferences.
"""
from sqlalchemy import Column, Integer, String, DateTime, Boolean, ARRAY, Text
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.models.database import Base

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    whatsapp_id = Column(String, unique=True, index=True, nullable=False)
    name = Column(String, nullable=True)
    diet = Column(String, nullable=True)  # veg, non-veg, both
    cuisine_pref = Column(String, nullable=True)  # north_indian, south_indian, etc.
    allergies = Column(ARRAY(String), nullable=True, server_default='{}')
    household_size = Column(String, nullable=True)  # single, couple, small_family, etc.
    onboarding_step = Column(Integer, nullable=True, default=0)  # 0-4 in progress, null means completed
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    last_active = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    pantry_items = relationship("UserPantry", back_populates="user", cascade="all, delete-orphan")
    sessions = relationship("Session", back_populates="user", cascade="all, delete-orphan")
    meal_plans = relationship("MealPlan", back_populates="user", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<User(whatsapp_id='{self.whatsapp_id}', name='{self.name}')>"