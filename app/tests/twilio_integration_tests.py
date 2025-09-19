#!/usr/bin/env python3
"""
Twilio integration tests: WhatsApp sending + webhook simulation.
"""
import sys, os
import asyncio

# Ensure project root on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from app.services.twilio_client import TwilioClient
from app.services.message_handler import MessageHandler


async def main():
    print("🧪 Twilio Integration Tests")
    client = TwilioClient()
    diag = client.test_connection()
    print("Twilio connection diagnostics:", diag)

    test_number = os.getenv("TEST_PHONE_NUMBER")
    if test_number:
        print(f"Sending WhatsApp message to {test_number}...")
        resp = client.send_whatsapp_message(test_number, "Mambo 🍽️ integration test")
        print("Send response:", resp)
    else:
        print("⚠️ Skipping send test (set TEST_PHONE_NUMBER env var to enable)")

    # Webhook simulation
    handler = MessageHandler()
    payload = {
        "entry": [
            {
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "messages": [
                                {
                                    "from": "+919152635928",
                                    "id": "SIM_TEST_1",
                                    "type": "text",
                                    "text": {"body": "What’s for dinner?"},
                                }
                            ]
                        },
                    }
                ]
            }
        ]
    }
    await handler.process_webhook(payload)
    print("✅ Webhook simulation processed successfully")


if __name__ == "__main__":
    asyncio.run(main())
