#!/usr/bin/env python3
"""
Endpoint tester (robust import). Run from project root or from anywhere.
Covers health, diagnostics, and Twilio webhook simulation.
"""
import sys
import os
import json
import time
from pathlib import Path
import asyncio
import httpx

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

BASE_URL = os.getenv("BASE_URL", "http://127.0.0.1:5000")
TEST_PHONE = os.getenv("TEST_PHONE", "+1234567890")


async def run_tests():
    async with httpx.AsyncClient(timeout=30.0) as client:
        print(f"🧪 Target: {BASE_URL}")

        # Root health
        print("\n🔍 Testing root '/' ...")
        r = await client.get(f"{BASE_URL}/")
        print("Root:", r.status_code, r.text)

        # Service health
        print("\n🔍 Testing /health ...")
        r = await client.get(f"{BASE_URL}/health")
        try:
            body = r.json()
        except Exception:
            body = r.text
        print("Health:", r.status_code, json.dumps(body, indent=2))

        # Diagnostics
        print("\n🔍 Testing /webhook/test ...")
        r = await client.get(f"{BASE_URL}/webhook/test")
        try:
            body = r.json()
        except Exception:
            body = r.text
        print("/webhook/test:", r.status_code, json.dumps(body, indent=2))

        # Simulated Twilio form webhook
        print("\n🔍 Simulated Twilio payload (debug)...")
        unique_sid = f"SM_TEST_{int(time.time())}"  # unique per run
        form = {
            "From": f"whatsapp:{TEST_PHONE}",
            "To": "whatsapp:+15550199202",
            "Body": "Hello Mambo!",
            "MessageSid": unique_sid,
            "NumMedia": "0",
        }
        r = await client.post(
            f"{BASE_URL}/webhook/whatsapp?debug=1",
            data=form,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        try:
            body = r.json()
        except Exception:
            body = r.text
        print("Webhook (debug):", r.status_code, json.dumps(body, indent=2))


if __name__ == "__main__":
    asyncio.run(run_tests())
