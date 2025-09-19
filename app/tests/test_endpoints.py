#!/usr/bin/env python3
"""
Endpoint tester (robust import). Run from project root or from anywhere.
"""
import sys
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import asyncio
import httpx
import os

BASE_URL = os.getenv("BASE_URL", "http://127.0.0.1:5000")
TEST_PHONE = os.getenv("TEST_PHONE", "+1234567890")


async def run_tests():
    async with httpx.AsyncClient(timeout=30.0) as client:
        print("🔍 Testing health endpoints...")
        r = await client.get(f"{BASE_URL}/health")
        print("Health:", r.status_code, r.text)

        print("🔍 Testing webhook /test...")
        r = await client.get(f"{BASE_URL}/webhook/test")
        print("/webhook/test:", r.status_code, r.text)

        print("🔍 Simulated Twilio payload (debug)...")
        r = await client.post(
            f"{BASE_URL}/webhook/whatsapp?debug=1",
            data={
                "From": f"whatsapp:{TEST_PHONE}",
                "To": "whatsapp:+15550199202",
                "Body": "Hello Mambo!",
                "MessageSid": "SM_TEST_123",
                "NumMedia": "0",
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        print("Webhook (debug) resp:", r.status_code, r.text)


if __name__ == "__main__":
    asyncio.run(run_tests())
