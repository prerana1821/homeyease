# tests/conftest.py
import asyncio
import types
from types import SimpleNamespace
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import app.config.settings as settings_mod


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(autouse=True)
def patch_settings(monkeypatch):
    """
    Provide sane defaults for settings used by services.
    Tests can override monkeypatch.setenv or monkeypatch attributes as needed.
    """
    monkeypatch.setattr(settings_mod, "openai_api_key", None, raising=False)
    monkeypatch.setattr(settings_mod, "openai_model", "gpt-5", raising=False)
    return monkeypatch


# --- Fake Supabase client ---
class FakeTable:

    def __init__(self):
        self._rows = []

    def insert(self, rows):
        # Accept dict or list
        rows = rows if isinstance(rows, list) else [rows]
        # Emulate returning success response object
        self._rows.extend(rows)
        return SimpleNamespace(data=rows, status_code=201)

    def upsert(self, data, on_conflict=None):
        # behave like insert for tests
        rows = data if isinstance(data, list) else [data]
        self._rows.extend(rows)
        return SimpleNamespace(data=rows, status_code=200)

    def select(self, *args, **kwargs):
        # return existing rows
        return SimpleNamespace(data=self._rows, status_code=200)

    def update(self, data):
        # naive: return updated object list
        return SimpleNamespace(data=[data], status_code=200)

    def delete(self):
        return SimpleNamespace(data=[], status_code=200)

    def eq(self, *args, **kwargs):
        return self

    def limit(self, n):
        return self

    def maybe_single(self):
        # return single if exists
        return self

    def in_(self, *args, **kwargs):
        return self


class FakeClient:

    def __init__(self):
        self._tables = {}

    def table(self, name):
        if name not in self._tables:
            self._tables[name] = FakeTable()
        return self._tables[name]

    def health_check(self):
        return True


@pytest.fixture
def fake_supabase_client(monkeypatch):
    fake = SimpleNamespace(client=FakeClient(), health_check=lambda: True)
    monkeypatch.setattr("app.config.supabase.supabase_client", fake)
    return fake


# --- Patch OpenAI client object shape used by our code ---
class DummyChoiceDict:

    def __init__(self, content):
        self.message = SimpleNamespace(content=content)


class DummyOpenAI:

    def __init__(self, api_key=None):
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, *args, **kwargs):
        # Return object similar to SDK: .choices list with .message.content
        return SimpleNamespace(choices=[DummyChoiceDict("WHATSDINNER")])


@pytest.fixture
def fake_openai(monkeypatch):
    # Expose class OpenAI to app.services.intent_classifier module dynamically during tests when needed
    monkeypatch.setattr(
        "app.services.intent_classifier.OpenAI", DummyOpenAI, raising=False
    )
    return DummyOpenAI


# --- Helper: patch google vision client in image_service ---
class FakeLabel:

    def __init__(self, desc, score):
        self.description = desc
        self.score = score


class FakeObject:

    def __init__(self, name, score):
        self.name = name
        self.score = score


class FakeVisionClient:

    def label_detection(self, image=None):
        # return object with label_annotations
        return SimpleNamespace(
            label_annotations=[FakeLabel("Tomato", 0.9), FakeLabel("Food", 0.8)]
        )

    def object_localization(self, image=None):
        return SimpleNamespace(
            localized_object_annotations=[
                FakeObject("Tomato", 0.8),
                FakeObject("Plate", 0.6),
            ]
        )


@pytest.fixture
def fake_vision(monkeypatch):
    monkeypatch.setattr(
        "app.services.image_service.vision",
        SimpleNamespace(Image=lambda **kw: None),
        raising=False,
    )
    # We'll patch the ImageService.client attribute per-test when needed
    return FakeVisionClient


# --- Patch httpx.AsyncClient.get for image download ---
@pytest.fixture
def patch_httpx_get(monkeypatch):

    async def _fake_get(url):

        class FakeResp:

            def __init__(self, content):
                self.content = content

            def raise_for_status(self):
                return None

        return FakeResp(b"\x89PNGFAKE")

    mock = AsyncMock(side_effect=_fake_get)
    monkeypatch.setattr("httpx.AsyncClient.get", mock)
    return mock
