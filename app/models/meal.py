"""
Meal model for storing meal information and recipes.
"""
from sqlalchemy import Column, Integer, String, ARRAY, Text
from app.models.database import Base

class Meal(Base):
    __tablename__ = "meals"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, index=True)
    cuisine = Column(String, nullable=False, index=True)
    ingredients = Column(ARRAY(String), nullable=False)
    tags = Column(ARRAY(String), nullable=True, server_default='{}')
    recipe_text = Column(Text, nullable=True)
    estimated_time_min = Column(Integer, nullable=True)
    diet_type = Column(String, nullable=False)  # veg, non-veg, both
    
    def __repr__(self):
        return f"<Meal(name='{self.name}', cuisine='{self.cuisine}')>"