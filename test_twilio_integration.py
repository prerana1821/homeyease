#!/usr/bin/env python3
"""
Test script specifically for Twilio integration.
Tests SMS and WhatsApp messaging via Twilio.
"""
import asyncio
import os
from app.services.twilio_client import TwilioClient
from app.services.hybrid_message_handler import HybridMessageHandler
from app.services.twilio_message_adapter import TwilioMessageAdapter

async def test_twilio_integration():
    """Test Twilio integration components."""
    print("🧪 Testing Twilio Integration...")
    
    # Test Twilio client
    print("\n📱 Testing Twilio Client...")
    twilio_client = TwilioClient()
    
    if twilio_client.client:
        print("✅ Twilio client initialized")
        
        # Test connection
        connection_ok = await twilio_client.test_connection()
        if connection_ok:
            print("✅ Twilio connection test passed")
        else:
            print("❌ Twilio connection test failed")
        
        # Test SMS sending (to your own number for testing)
        test_phone = os.getenv("TEST_PHONE_NUMBER")  # Set this in your .env
        if test_phone:
            print(f"\n📤 Testing SMS to {test_phone}...")
            sms_sent = await twilio_client.send_sms(
                test_phone, 
                "Mambo 🤖: This is a test message from your meal planning bot!"
            )
            if sms_sent:
                print("✅ SMS sent successfully")
            else:
                print("❌ SMS sending failed")
        else:
            print("⚠️ No TEST_PHONE_NUMBER set, skipping SMS test")
    else:
        print("❌ Twilio client not initialized - check credentials")
    
    # Test message adapter
    print("\n🔄 Testing Message Adapter...")
    adapter = TwilioMessageAdapter()
    
    # Test SMS to WhatsApp format conversion
    test_sms = adapter.convert_sms_to_whatsapp_format(
        from_phone="+1234567890",
        body="What should I cook for dinner?",
        message_sid="test_sid_123"
    )
    
    if test_sms.get("entry"):
        print("✅ SMS to WhatsApp format conversion works")
    else:
        print("❌ SMS to WhatsApp format conversion failed")
    
    # Test interactive response parsing
    interactive_response = adapter._parse_interactive_response("1")
    if interactive_response:
        print("✅ Interactive response parsing works")
    else:
        print("❌ Interactive response parsing failed")
    
    # Test hybrid message handler
    print("\n🔀 Testing Hybrid Message Handler...")
    hybrid_handler = HybridMessageHandler()
    
    channel_status = await hybrid_handler.get_channel_status()
    print(f"📊 Channel Status: {channel_status}")
    
    if test_phone:
        print(f"\n📤 Testing hybrid messaging to {test_phone}...")
        message_sent = await hybrid_handler.send_message_via_best_channel(
            test_phone,
            "Mambo 🍽️: This is a test from the hybrid message handler!"
        )
        if message_sent:
            print("✅ Hybrid message sent successfully")
        else:
            print("❌ Hybrid message sending failed")
    
    print("\n🎯 Twilio Integration Test Complete!")

async def test_webhook_simulation():
    """Simulate Twilio webhook calls."""
    print("\n🌐 Testing Webhook Simulation...")
    
    from app.services.message_handler import MessageHandler
    
    adapter = TwilioMessageAdapter()
    handler = MessageHandler()
    
    # Simulate SMS webhook
    sms_webhook = adapter.convert_sms_to_whatsapp_format(
        from_phone="+1234567890",
        body="Hello Mambo!",
        message_sid="test_sms_123"
    )
    
    try:
        await handler.process_webhook(sms_webhook)
        print("✅ SMS webhook simulation successful")
    except Exception as e:
        print(f"❌ SMS webhook simulation failed: {e}")
    
    # Simulate WhatsApp webhook
    whatsapp_webhook = adapter.convert_whatsapp_to_whatsapp_format(
        from_phone="whatsapp:+1234567890",
        body="What's for dinner?",
        message_sid="test_wa_123"
    )
    
    try:
        await handler.process_webhook(whatsapp_webhook)
        print("✅ WhatsApp webhook simulation successful")
    except Exception as e:
        print(f"❌ WhatsApp webhook simulation failed: {e}")

if __name__ == "__main__":
    print("🚀 Starting Twilio Integration Tests...")
    asyncio.run(test_twilio_integration())
    asyncio.run(test_webhook_simulation())