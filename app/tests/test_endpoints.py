#!/usr/bin/env python3
"""
Lightweight smoke test for Mambo bot endpoints.
Useful for quick health + webhook checks against a running server.
"""
import sys
import os
import asyncio
from pathlib import Path
import httpx

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

BASE_URL = os.getenv("BASE_URL", "http://127.0.0.1:5000")
TEST_PHONE = os.getenv("TEST_PHONE", "+1234567890")


async def run_tests():
    async with httpx.AsyncClient(timeout=10.0) as client:
        print(f"🔍 Smoke test against {BASE_URL}")

        try:
            r = await client.get(f"{BASE_URL}/health")
            print("Health:", r.status_code, r.text[:200])
        except Exception as e:
            print("Health check failed:", e)

        try:
            r = await client.get(f"{BASE_URL}/webhook/test")
            print("/webhook/test:", r.status_code, r.text[:200])
        except Exception as e:
            print("/webhook/test failed:", e)

        try:
            form = {
                "From": f"whatsapp:{TEST_PHONE}",
                "To": "whatsapp:+15550199202",
                "Body": "Hello Mambo!",
                "MessageSid": "SM_TEST_SMOKE_1",
                "NumMedia": "0",
            }
            r = await client.post(
                f"{BASE_URL}/webhook/whatsapp?debug=1",
                data=form,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            print("Webhook (debug):", r.status_code, r.text[:200])
        except Exception as e:
            print("Webhook test failed:", e)


if __name__ == "__main__":
    asyncio.run(run_tests())
