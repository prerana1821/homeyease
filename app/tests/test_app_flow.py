# app/tests/test_app_flow.py
import pytest
from app.services.user_service import UserService
from app.services.onboarding_service import OnboardingService
from app.services.message_handler import MessageHandler

from app.tests.test_user_service import FakeDB


@pytest.fixture
def deps():
    db = FakeDB()
    us = UserService(db)
    osvc = OnboardingService(us)
    mh = MessageHandler(db, us, osvc)
    return {"db": db, "us": us, "osvc": osvc, "mh": mh}


def test_message_onboarding_flow_persists(deps):
    mh = deps["mh"]
    db = deps["db"]
    wa = "msg_wa_1"
    message = {
        "whatsapp_id": wa,
        "text": "My diet is vegetarian",
        "onboarding_step": 1,
        "onboarding_payload": {"diet": "vegetarian"},
    }
    resp = mh.handle_incoming_message(message)
    assert resp["ok"]
    # ensure user created and onboarding persisted
    us = deps["us"]
    u = us.get_user(whatsapp_id=wa)
    assert u["ok"] and u["data"]["diet"] == "vegetarian"
    # ensure a session was created
    sessions = db.tables.get("sessions", [])
    assert len(sessions) >= 1
    assert sessions[0]["prompt"] == "My diet is vegetarian"
    assert (
        "onboarding step 1 result" in sessions[0]["response"]
        or sessions[0]["response"] is not None
    )
