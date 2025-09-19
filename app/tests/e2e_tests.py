#!/usr/bin/env python3
"""
Integrated E2E test runner for the Mambo bot (Twilio-only).
Runs a sequence of checks against a local or remote running server.

Usage:
  BASE_URL=http://127.0.0.1:5000 TEST_PHONE="+12345678901" python tools/mambo_e2e_tester.py
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

BASE_URL = os.getenv("BASE_URL", "http://127.0.0.1:5000")
TEST_PHONE = os.getenv("TEST_PHONE", "+12345678901")


class MamboBotTester:

    def __init__(self):
        self.client = httpx.AsyncClient(timeout=10.0)
        self.test_results = []

    async def log_test(self, name: str, ok: bool, details: str = ""):
        status = "✅ PASS" if ok else "❌ FAIL"
        print(f"{status} {name}{' - ' + details if details else ''}")
        self.test_results.append({
            "test": name,
            "ok": ok,
            "details": details,
            "ts": datetime.utcnow().isoformat(),
        })

    async def test_health(self):
        print("\n🔍 Testing health endpoints...")
        try:
            r = await self.client.get(f"{BASE_URL}/")
            await self.log_test("root", r.status_code == 200,
                                f"status={r.status_code}")
        except Exception as e:
            await self.log_test("root", False, str(e))

        try:
            r = await self.client.get(f"{BASE_URL}/health")
            ok = r.status_code in (200, 503)
            body = {}
            try:
                body = r.json()
            except Exception:
                pass
            await self.log_test(
                "health", r.status_code == 200,
                f"status={r.status_code} db={body.get('database')}")
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
        form = {
            "From": f"whatsapp:{TEST_PHONE}",
            "To": "whatsapp:+15550199202",
            "Body": "Hi",
            "MessageSid": "SM_TEST_ONBOARD_1",
            "NumMedia": "0",
        }
        try:
            r = await self.client.post(f"{BASE_URL}/webhook/whatsapp?debug=1",
                                       data=form)
            await self.log_test("webhook_onboarding_form",
                                r.status_code == 200,
                                f"status={r.status_code}")
        except Exception as e:
            await self.log_test("webhook_onboarding_form", False, str(e))

        form2 = {
            "From": f"whatsapp:{TEST_PHONE}",
            "To": "whatsapp:+15550199202",
            "Body": "What should I cook for dinner?",
            "MessageSid": "SM_TEST_MEALREQ_1",
            "NumMedia": "0",
        }
        try:
            r = await self.client.post(f"{BASE_URL}/webhook/whatsapp?debug=1",
                                       data=form2)
            await self.log_test("webhook_meal_request_form",
                                r.status_code == 200,
                                f"status={r.status_code}")
        except Exception as e:
            await self.log_test("webhook_meal_request_form", False, str(e))

    async def run_all(self):
        print("🧪 Running Mambo Bot E2E tests")
        print(f"Target: {BASE_URL}")
        await self.test_health()
        await self.test_webhook_diagnostics()
        await self.test_whatsapp_webhook_form()

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
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main())
