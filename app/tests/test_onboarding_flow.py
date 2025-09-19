# app/tests/test_onboarding_flow.py
import pytest
from app.services.user_service import UserService
from app.services.onboarding_service import OnboardingService


class FakeDBForOnboard:
    # reuse simple FakeDB shape used in previous test
    def __init__(self):
        self.tables = {}
        self.counters = {}

    def table(self, name):
        # import the FakeTable from previous test module if available, else create trivial proxy
        from app.tests.test_user_service import FakeTable

        return FakeTable(self, name)

    def next_id(self, name):
        self.counters.setdefault(name, 0)
        self.counters[name] += 1
        return self.counters[name]


@pytest.fixture
def user_service():
    db = FakeDBForOnboard()
    return UserService(db)


@pytest.fixture
def onboarding_service(user_service):
    return OnboardingService(user_service)


def test_onboarding_steps_persist(onboarding_service, user_service):
    wa = "onboard_1"
    # step 1: diet
    r1 = onboarding_service.process_step(wa, 1, {"diet": "vegetarian"})
    assert r1["ok"]
    u = user_service.get_user(whatsapp_id=wa)
    assert u["ok"] and u["data"]["diet"] == "vegetarian"
    assert u["data"]["onboarding_step"] == 1

    # step 2: cuisines
    r2 = onboarding_service.process_step(wa, 2, {"cuisine_pref": "Indian, Italian"})
    assert r2["ok"]
    u = user_service.get_user(whatsapp_id=wa)
    assert "Indian" in u["data"]["cuisine_pref"]

    # step 3: allergies
    r3 = onboarding_service.process_step(wa, 3, {"allergies": ["peanut"]})
    assert r3["ok"]
    u = user_service.get_user(whatsapp_id=wa)
    assert "peanut" in str(u["data"]["allergies"])

    # step 4: household size
    r4 = onboarding_service.process_step(wa, 4, {"household_size": 4})
    assert r4["ok"]
    u = user_service.get_user(whatsapp_id=wa)
    assert u["data"]["household_size"] == "4"
