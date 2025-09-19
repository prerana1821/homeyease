#!/usr/bin/env python3
"""
Simple TwilioClient smoke test.
"""
import sys, os
import asyncio

# Ensure root of project is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from app.services.twilio_client import TwilioClient


async def main():
    client = TwilioClient()
    print("Twilio client initialized:", bool(client.client))

    # Test connection (sync method, so call without await)
    diag = client.test_connection()
    print("Connection diagnostics:", diag)

    # Try sending a WhatsApp message if env var is set
    test_number = os.getenv("TEST_PHONE_NUMBER")
    if test_number:
        print(f"Sending WhatsApp test to {test_number}...")
        resp = client.send_whatsapp_message(
            test_number, "Mambo 🤖 test message from TwilioClient"
        )
        print("Send response:", resp)
    else:
        print("No TEST_PHONE_NUMBER set; skipping send test")


if __name__ == "__main__":
    asyncio.run(main())
