# tests/test_recommendation_service.py
import pytest
from unittest.mock import AsyncMock, MagicMock
from app.services.recommendation_service import RecommendationService


@pytest.mark.asyncio
async def test_get_meal_recommendations(monkeypatch):
    svc = RecommendationService()
    # stub user_service to return a user dict compatible with old code
    fake_user = {
        "id": 1,
        "diet": "veg",
        "cuisine_pref": "north_indian",
        "allergies": [],
        "household_size": "single",
    }
    monkeypatch.setattr(
        svc,
        "user_service",
        MagicMock(
            get_user_by_whatsapp_id=AsyncMock(
                return_value={"ok": True, "data": fake_user}
            )
        ),
    )
    # stub classifier
    monkeypatch.setattr(
        svc,
        "intent_classifier",
        MagicMock(classify_intent=AsyncMock(return_value="MOOD")),
    )
    # stub meal_service: return a couple of meals
    fake_meals = [
        {
            "name": "Spicy Paneer",
            "cuisine": "north_indian",
            "diet_type": "veg",
            "tags": ["spicy"],
            "ingredients": ["paneer", "chili"],
            "estimated_time_min": 25,
        },
        {
            "name": "Dal Tadka",
            "cuisine": "north_indian",
            "diet_type": "veg",
            "tags": ["comfort"],
            "ingredients": ["dal"],
            "estimated_time_min": 30,
        },
    ]
    monkeypatch.setattr(
        svc, "meal_service", MagicMock(search_meals=AsyncMock(return_value=fake_meals))
    )
    res = await svc.get_meal_recommendations("+9112345", "I am in the mood for spicy")
    assert isinstance(res, list)
    assert len(res) > 0
    assert any("Spicy" in (m.get("name") or "") for m in res)
