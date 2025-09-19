#!/usr/bin/env python3
"""
Simple TwilioClient smoke test.

Run: python scripts/test_twilio_client.py
Make sure env vars are set:
  - TWILIO_ACCOUNT_SID
  - TWILIO_AUTH_TOKEN
  - TWILIO_PHONE_NUMBER
Optionally:
  - TEST_PHONE_NUMBER (a verified WhatsApp number in your Twilio sandbox)
"""
import os
import sys

# Ensure root of project is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from app.services.twilio_client import TwilioClient


def main():
    # Initialize client
    client = TwilioClient()
    print("✅ Twilio client initialized:", bool(client.client))

    # Check which env vars are set
    env_diag = {
        "TWILIO_ACCOUNT_SID": bool(os.getenv("TWILIO_ACCOUNT_SID")),
        "TWILIO_AUTH_TOKEN": bool(os.getenv("TWILIO_AUTH_TOKEN")),
        "TWILIO_PHONE_NUMBER": bool(os.getenv("TWILIO_PHONE_NUMBER")),
    }
    print("🔑 Env vars present:", env_diag)

    # Test connection
    diag = client.test_connection()
    print("🔍 Connection diagnostics:", diag)

    # Optional send test
    test_number = os.getenv("TEST_PHONE_NUMBER")
    if test_number:
        print(f"📨 Sending WhatsApp test to {test_number} ...")
        resp = client.send_whatsapp_message(
            test_number, "Mambo 🤖 test message from TwilioClient"
        )
        print("Send response:", resp)
    else:
        print("⚠️ No TEST_PHONE_NUMBER set; skipping send test")


if __name__ == "__main__":
    main()
