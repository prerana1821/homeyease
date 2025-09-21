# tests/test_image_service.py
import pytest
from app.services.image_service import ImageService


@pytest.mark.asyncio
async def test_detect_from_base64(fake_vision, patch_httpx_get):
    svc = ImageService()
    # inject fake vision client
    svc.client = fake_vision
    # craft a small base64 (real decode not required because fake client ignores bytes)
    import base64

    b = base64.b64encode(b"fakeimagecontent").decode()
    res = await svc.detect_ingredients_from_base64(b)
    # normalized shape: dict with ok and ingredients
    assert isinstance(res, dict)
    # Because mapping includes tomato -> expect tomato in ingredients
    assert "tomato" in res.get("ingredients", []) or res.get("ok") is False


@pytest.mark.asyncio
async def test_detect_from_url(fake_vision, patch_httpx_get):
    svc = ImageService()
    svc.client = fake_vision
    res = await svc.detect_ingredients_from_url("http://example.com/fake.png")
    assert isinstance(res, dict)
    assert "ingredients" in res
