"""
User pantry model for tracking ingredients.
"""
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.models.database import Base

class UserPantry(Base):
    __tablename__ = "user_pantry"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    ingredient = Column(String, nullable=False)
    quantity = Column(String, nullable=True)
    last_seen = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationship
    user = relationship("User", back_populates="pantry_items")
    
    # Unique constraint
    __table_args__ = (UniqueConstraint('user_id', 'ingredient', name='_user_ingredient_uc'),)
    
    def __repr__(self):
        return f"<UserPantry(user_id={self.user_id}, ingredient='{self.ingredient}')>"