# app/tests/test_twilio_webhook_integration.py
"""
Integration-style tests for Twilio webhook + message handling.

Modes:
- pytest (default): run tests with FakeDB + FastAPI TestClient (no external network).
- script (LIVE=1): run as a script for local/dev; can optionally send a real WhatsApp
  message if TEST_PHONE_NUMBER is set. By default the webhook processing still uses
  the FakeDB unless you set USE_REAL_DB=1 (danger: will write to your real DB).

Usage:
  # run automated tests (CI)
  pytest -q app/tests/test_twilio_webhook_integration.py

  # local dev live mode (optional)
  LIVE=1 TEST_PHONE_NUMBER="+9198..." python app/tests/test_twilio_webhook_integration.py
"""
from __future__ import annotations

import os
import sys
import json
import asyncio
import logging
from typing import Any, Dict, List

# Make sure repo root is importable when run as script
if __name__ == "__main__" and __package__ is None:
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)

import pytest
from fastapi.testclient import TestClient

# Import the app FastAPI instance. Adjust if your app entrypoint differs.
try:
    from app.main import app  # common pattern
except Exception:
    # If you don't have app.main, try alternate import
    from app import main as _main  # type: ignore

    app = getattr(_main, "app", None)
    if app is None:
        raise RuntimeError("Unable to import FastAPI `app` from app.main")

# Services under test
from app.services.user_service import UserService
from app.services.message_handler import MessageHandler
from app.services.onboarding_service import OnboardingService
from app.services.twilio_client import TwilioClient


# ---------------------------------------------------------------------
# Small in-memory FakeDB and FakeTable (used for CI-safe testing)
# ---------------------------------------------------------------------
class FakeTable:

    def __init__(self, db, name):
        self.db = db
        self.name = name
        self._where = {}
        self._operation = None
        self._limit = None

    # Query building (chainable)
    def select(self, *args, **kwargs):
        return self

    def eq(self, col, val):
        self._where[col] = val
        return self

    def limit(self, n):
        self._limit = n
        return self

    def insert(self, payload):
        self._operation = ("insert", payload)
        return self

    def update(self, payload):
        self._operation = ("update", payload)
        return self

    def upsert(self, payload, on_conflict=None):
        self._operation = ("upsert", payload, on_conflict)
        return self

    def delete(self):
        self._operation = ("delete", None)
        return self

    def execute(self):
        op = getattr(self, "_operation", None)
        if not op:
            # select
            rows = []
            for r in self.db.tables.get(self.name, []):
                match = True
                for k, v in getattr(self, "_where", {}).items():
                    if str(r.get(k)) != str(v):
                        match = False
                        break
                if match:
                    rows.append(r)
            if self._limit:
                rows = rows[: self._limit]
            return {"data": rows}
        typ = op[0]
        if typ == "insert":
            payload = dict(op[1])
            payload["id"] = self.db.next_id(self.name)
            self.db.tables.setdefault(self.name, []).append(payload)
            return {"data": [payload]}
        if typ == "update":
            payload = op[1]
            updated = []
            for r in self.db.tables.get(self.name, []):
                match = True
                for k, v in getattr(self, "_where", {}).items():
                    if str(r.get(k)) != str(v):
                        match = False
                        break
                if match:
                    r.update(payload)
                    updated.append(r)
            return {"data": updated}
        if typ == "upsert":
            payload = op[1]
            on_conflict = op[2]
            key = on_conflict
            found = None
            for r in self.db.tables.get(self.name, []):
                if key and key in payload and str(r.get(key)) == str(payload.get(key)):
                    found = r
                    break
            if found:
                found.update(payload)
                return {"data": [found]}
            else:
                payload["id"] = self.db.next_id(self.name)
                self.db.tables.setdefault(self.name, []).append(dict(payload))
                return {"data": [payload]}
        if typ == "delete":
            new_rows = []
            deleted = []
            for r in self.db.tables.get(self.name, []):
                match = True
                for k, v in getattr(self, "_where", {}).items():
                    if str(r.get(k)) != str(v):
                        match = False
                        break
                if match:
                    deleted.append(r)
                else:
                    new_rows.append(r)
            self.db.tables[self.name] = new_rows
            return {"data": deleted}
        return {"data": []}


class FakeDB:

    def __init__(self):
        self.tables: Dict[str, List[Dict[str, Any]]] = {}
        self.counters: Dict[str, int] = {}

    def table(self, name):
        return FakeTable(self, name)

    def next_id(self, name):
        self.counters.setdefault(name, 0)
        self.counters[name] += 1
        return self.counters[name]

    # Minimal health_check used by webhook test endpoint
    def health_check(self):
        return True


# ---------------------------------------------------------------------
# Fixtures for pytest
# ---------------------------------------------------------------------
@pytest.fixture
def fake_db():
    return FakeDB()


@pytest.fixture
def wired_app(fake_db, monkeypatch):
    """
    Return a TestClient with the webhook module patched to use FakeDB-backed services.

    We patch the module-level singletons in app.api.twilio_webhook if present.
    """
    # Patch the supabase_client used by the API module if present
    try:
        import app.api.twilio_webhook as tb
    except Exception:
        raise

    # Create our fake UserService / OnboardingService / MessageHandler using FakeDB
    user_svc = UserService(fake_db)
    onboard_svc = OnboardingService(user_svc)
    mh = MessageHandler(
        db_client=fake_db, user_service=user_svc, onboarding_service=onboard_svc
    )

    # Monkeypatch singletons in the module
    monkeypatch.setattr(tb, "_user_service", user_svc, raising=False)
    monkeypatch.setattr(tb, "_onboarding_service", onboard_svc, raising=False)
    monkeypatch.setattr(tb, "message_handler", mh, raising=False)
    monkeypatch.setattr(tb, "supabase_client", fake_db, raising=False)

    client = TestClient(app)
    return client, fake_db, mh


# ---------------------------------------------------------------------
# Automated pytest tests (CI-safe)
# ---------------------------------------------------------------------
def test_whatsapp_webhook_creates_user_and_session(wired_app):
    client, fake_db, mh = wired_app
    form_data = {
        "From": "whatsapp:+919152635928",
        "To": "whatsapp:+19998887777",
        "Body": "I am vegetarian",
        "MessageSid": "SM_TEST_12345",
        "NumMedia": "0",
    }

    resp = client.post("/whatsapp", data=form_data)
    assert (
        resp.status_code == 200
    ), f"unexpected status: {resp.status_code} / {resp.text}"

    # Check user created
    users = fake_db.tables.get("users", [])
    assert len(users) == 1, f"expected 1 user, got {len(users)}"
    assert users[0]["whatsapp_id"].endswith("9152635928") or users[0][
        "whatsapp_id"
    ].endswith("9152635928".lstrip("+"))

    # Check session log created and raw payload saved
    sessions = fake_db.tables.get("sessions", [])
    assert len(sessions) == 1
    assert sessions[0]["prompt"] == "I am vegetarian"
    assert "MessageSid" in sessions[0].get("raw_payload", sessions[0].get("raw", {}))


def test_onboarding_step_persistent(wired_app):
    # Simulate onboarding payload posted to webhook
    client, fake_db, mh = wired_app
    form_data = {
        "From": "whatsapp:+919199999999",
        "To": "whatsapp:+19998887777",
        # We'll encode an onboarding step inside Body as a small JSON marker for tests.
        # In production you'd probably have structured handlers; here MessageHandler inspects message dict.
        "Body": json.dumps(
            {"onboarding_step": 1, "onboarding_payload": {"diet": "vegan"}}
        ),
        "MessageSid": "SM_ONBOARD_1",
        "NumMedia": "0",
    }
    resp = client.post("/whatsapp", data=form_data)
    assert resp.status_code == 200

    # The webhook transforms Body into text. The MessageHandler in our code expects message text,
    # but our earlier MessageHandler.handle_incoming_message looks for onboarding_step in the message dict.
    # The test ensures that when the MessageHandler receives a prepared incoming_message with onboarding keys,
    # the OnboardingService persists the user record.
    # In our webhook pipeline, Body is plain text; to simulate the actionable onboarding call we will call the handler directly:
    incoming_message = {
        "whatsapp_id": "919199999999",
        "id": "SIM_ONBOARD_1",
        "timestamp": str(int(time.time())),
        "type": "text",
        "text": None,
        "raw": form_data,
        # mimic the structure MessageHandler expects for onboarding
        "onboarding_step": 1,
        "onboarding_payload": {"diet": "vegan"},
    }
    # call handler directly (this uses fake_db)
    res = mh.handle_incoming_message(incoming_message)
    assert res["ok"]

    users = fake_db.tables.get("users", [])
    assert len(users) == 1
    assert users[0].get("diet") == "vegan"
    assert users[0].get("onboarding_step") == 1


# ---------------------------------------------------------------------
# Script / interactive mode (LIVE=1)
# ---------------------------------------------------------------------
async def _run_live_mode():
    """
    Developer-friendly mode that optionally sends a real Twilio message (if TEST_PHONE_NUMBER set),
    then simulates a webhook invocation locally (but still uses FakeDB unless you set USE_REAL_DB=1).
    """
    print("=== Twilio webhook integration - LIVE mode ===")
    test_phone = os.getenv("TEST_PHONE_NUMBER")
    use_real_db = os.getenv("USE_REAL_DB") == "1"
    # Initialize Twilio client (uses configured settings)
    tclient = TwilioClient()

    # Optionally send a real WhatsApp message (requires Twilio configured)
    if test_phone:
        print(f"Sending real WhatsApp to {test_phone} (via Twilio)...")
        # Use sync send (TwilioClient provides async wrapper too)
        send_resp = tclient.send_whatsapp_message(
            test_phone, "Mambo 🍽️ integration smoke test"
        )
        print("-> send response:", send_resp)
    else:
        print("TEST_PHONE_NUMBER not set; skipping real-send step.")

    # Prepare DB (fake or real)
    if use_real_db:
        print(
            "USE_REAL_DB=1 set: WILL USE real supabase_client if available (danger: writes to production DB)"
        )
        try:
            # prefer the imported supabase client if available in app.api.twilio_webhook
            import app.api.twilio_webhook as tbmod  # type: ignore

            real_db = getattr(tbmod, "supabase_client", None)
            if real_db is None:
                print(
                    "No supabase_client found in app.api.twilio_webhook; falling back to FakeDB"
                )
                use_real_db = False
        except Exception:
            print("Unable to find supabase_client; falling back to FakeDB")
            use_real_db = False

    if not use_real_db:
        db = FakeDB()
        user_svc = UserService(db)
        onboard_svc = OnboardingService(user_svc)
        mh = MessageHandler(
            db_client=db, user_service=user_svc, onboarding_service=onboard_svc
        )
    else:
        # risk: writing to real DB
        from app.api.twilio_webhook import supabase_client as db  # type: ignore

        user_svc = UserService(db)
        onboard_svc = OnboardingService(user_svc)
        mh = MessageHandler(
            db_client=db, user_service=user_svc, onboarding_service=onboard_svc
        )

    # Simulate incoming Twilio webhook payload
    simulated_form = {
        "From": "whatsapp:+919152635928",
        "To": "whatsapp:+19998887777",
        "Body": "Hi Mambo — what's for dinner?",
        "MessageSid": "SM_SIMULATED_9999",
        "NumMedia": "0",
    }
    # Build same internal message as webhook does
    incoming_message = {
        "whatsapp_id": simulated_form["From"].replace("whatsapp:", ""),
        "id": simulated_form["MessageSid"],
        "timestamp": str(int(time.time())),
        "type": "text",
        "text": simulated_form["Body"],
        "raw": simulated_form,
    }

    print(
        "Invoking MessageHandler.process_webhook equivalent (handle_incoming_message)..."
    )
    result = mh.handle_incoming_message(incoming_message)
    print("Handler result:", result)

    # Inspect DB
    if not use_real_db:
        print("FakeDB users:", db.tables.get("users", []))
        print("FakeDB sessions:", db.tables.get("sessions", []))
    else:
        print("Wrote to real DB — inspect your Supabase console for users/sessions.")


# ---------------------------------------------------------------------
# Entrypoint for script mode
# ---------------------------------------------------------------------
if __name__ == "__main__" and os.getenv("LIVE") == "1":
    # Run interactive live mode
    logging.basicConfig(level=logging.INFO)
    asyncio.run(_run_live_mode())
