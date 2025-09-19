#!/usr/bin/env python3
"""
Integrated test runner for the Mambo bot (Twilio-only).
Runs a sequence of checks against a local running server.
"""
import asyncio
import os
from datetime import datetime
import sys
from pathlib import Path
import httpx

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Configuration
BASE_URL = os.getenv("MAMBO_BASE_URL", "http://127.0.0.1:5000")
TEST_PHONE = os.getenv("TEST_PHONE", "+12345678901")  # use a safe test number


class MamboBotTester:

    def __init__(self):
        # Use one client for all tests
        self.client = httpx.AsyncClient(timeout=10.0)
        self.test_results = []

    async def log_test(self, name: str, ok: bool, details: str = ""):
        status = "✅ PASS" if ok else "❌ FAIL"
        print(f"{status} {name}{' - ' + details if details else ''}")
        self.test_results.append(
            {
                "test": name,
                "ok": ok,
                "details": details,
                "ts": datetime.utcnow().isoformat(),
            }
        )

    async def test_health(self):
        print("\n🔍 Testing health endpoints...")
        try:
            r = await self.client.get(f"{BASE_URL}/")
            await self.log_test("root", r.status_code == 200, f"status={r.status_code}")
        except Exception as e:
            await self.log_test("root", False, str(e))

        try:
            r = await self.client.get(f"{BASE_URL}/health")
            ok = r.status_code in (200, 503)
            body = r.json() if ok else {}
            await self.log_test(
                "health",
                r.status_code == 200,
                f"status={r.status_code} db={body.get('database')}",
            )
        except Exception as e:
            await self.log_test("health", False, str(e))

    async def test_webhook_diagnostics(self):
        print("\n🔍 Testing webhook diagnostics (/webhook/test)...")
        try:
            r = await self.client.get(f"{BASE_URL}/webhook/test")
            ok = r.status_code == 200
            await self.log_test("/webhook/test", ok, f"status={r.status_code}")
        except Exception as e:
            await self.log_test("/webhook/test", False, str(e))

    async def test_whatsapp_webhook_form(self):
        print(
            "\n🔍 Testing Twilio-form webhook (simulated incoming WhatsApp message)..."
        )
        # Simulate Twilio form-encoded webhook for a new user (onboarding start).
        form = {
            "From": f"whatsapp:{TEST_PHONE}",
            "To": "whatsapp:+15550199202",
            "Body": "Hi",
            "MessageSid": "SM_TEST_ONBOARD_1",
            "NumMedia": "0",
        }
        try:
            r = await self.client.post(
                f"{BASE_URL}/webhook/whatsapp?debug=1", data=form
            )
            ok = r.status_code == 200
            details = r.text[:400]
            await self.log_test(
                "webhook_onboarding_form",
                ok,
                f"status={r.status_code} data_preview={details}",
            )
        except Exception as e:
            await self.log_test("webhook_onboarding_form", False, str(e))

        # Simulate a follow-up message (meal request)
        form2 = {
            "From": f"whatsapp:{TEST_PHONE}",
            "To": "whatsapp:+15550199202",
            "Body": "What should I cook for dinner?",
            "MessageSid": "SM_TEST_MEALREQ_1",
            "NumMedia": "0",
        }
        try:
            r = await self.client.post(
                f"{BASE_URL}/webhook/whatsapp?debug=1", data=form2
            )
            ok = r.status_code == 200
            await self.log_test(
                "webhook_meal_request_form", ok, f"status={r.status_code}"
            )
        except Exception as e:
            await self.log_test("webhook_meal_request_form", False, str(e))

    async def test_intent_classifier(self):
        print("\n🔍 Testing intent classifier (if available)...")
        try:
            from app.services.intent_classifier import IntentClassifier  # may raise

            classifier = IntentClassifier()
            sample = "What should I eat for dinner?"
            try:
                result = await classifier.classify_intent(sample)
                await self.log_test("intent_classifier_basic", True, f"result={result}")
            except Exception as e:
                await self.log_test("intent_classifier_basic", False, str(e))
        except Exception as e:
            await self.log_test(
                "intent_classifier_import", False, "not available or error: " + str(e)
            )

    async def test_database_ops(self):
        print(
            "\n🔍 Testing database operations via UserService (if Supabase configured)..."
        )
        try:
            from app.services.user_service import UserService

            user_svc = UserService()
            # create user
            res = await user_svc.create_user(TEST_PHONE, name="Test User")
            ok = res.get("ok") and res.get("result") is not None
            await self.log_test("user_create", ok, f"diag={res.get('diagnostics')}")
        except Exception as e:
            await self.log_test("user_create", False, str(e))

    async def run_all(self):
        print("🧪 Running Mambo Bot E2E tests")
        print(f"Target: {BASE_URL}")
        await self.test_health()
        await self.test_webhook_diagnostics()
        await self.test_whatsapp_webhook_form()
        await self.test_intent_classifier()
        await self.test_database_ops()

        # Summary
        passed = sum(1 for t in self.test_results if t["ok"])
        total = len(self.test_results)
        print(f"\n📊 Summary: {passed}/{total} tests passed")
        if passed < total:
            print("Failed tests details:")
            for t in self.test_results:
                if not t["ok"]:
                    print(f" - {t['test']}: {t['details']}")
        await self.client.aclose()
        return passed == total


async def main():
    runner = MamboBotTester()
    success = await runner.run_all()
    if success:
        print("\n🎉 All checks passed")
    else:
        print("\n⚠️ Some checks failed")
    return success


if __name__ == "__main__":
    asyncio.run(main())
