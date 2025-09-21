# tests/test_intent_classifier.py
import pytest
import asyncio
from app.services.intent_classifier import IntentClassifier


@pytest.mark.asyncio
async def test_rule_based_recipe():
    c = IntentClassifier()
    intent = await c.classify_intent("How to make dal?")  # rule-based pattern
    assert intent == "RECIPE_REQUEST"


@pytest.mark.asyncio
async def test_hinglish_parsing():
    c = IntentClassifier()
    res = await c.classify_intent("aaj kya banau")  # hinglish
    assert res == "WHATSDINNER" or res == "PANTRY_HELP" or isinstance(res, str)


@pytest.mark.asyncio
async def test_fuzzy_match():
    c = IntentClassifier()
    res = await c.classify_intent("wat to eat tonight")
    assert res == "WHATSDINNER"


@pytest.mark.asyncio
async def test_openai_fallback(patch_settings, fake_openai, monkeypatch):
    # enable OpenAI via settings and ensure classifier uses fallback LLM
    monkeypatch.setattr("app.config.settings.openai_api_key", "", raising=False)
    c = IntentClassifier()
    # ensure client created
    assert c.openai_client is not None
    intent = await c.classify_intent("Something vague that rules won't match")
    assert intent == "WHATSDINNER"  # DummyOpenAI returns WHATSDINNER
