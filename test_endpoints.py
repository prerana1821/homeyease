#!/usr/bin/env python3
"""
Test script for Mambo Bot endpoints and functionality.
Run this to verify all components are working correctly.
"""
import asyncio
import json
import httpx
import os
from datetime import datetime

# Test configuration
BASE_URL = "http://127.0.0.1:5000"
TEST_PHONE = "+1234567890"  # Test phone number

class MamboBotTester:
    def __init__(self):
        self.client = httpx.AsyncClient()
        self.test_results = []
    
    async def log_test(self, test_name: str, success: bool, details: str = ""):
        """Log test results."""
        status = "✅ PASS" if success else "❌ FAIL"
        result = f"{status} {test_name}"
        if details:
            result += f" - {details}"
        print(result)
        self.test_results.append({
            "test": test_name,
            "success": success,
            "details": details,
            "timestamp": datetime.now().isoformat()
        })
    
    async def test_health_endpoints(self):
        """Test basic health endpoints."""
        print("\n🔍 Testing Health Endpoints...")
        
        # Test root endpoint
        try:
            response = await self.client.get(f"{BASE_URL}/")
            success = response.status_code == 200
            await self.log_test("Root endpoint", success, f"Status: {response.status_code}")
        except Exception as e:
            await self.log_test("Root endpoint", False, str(e))
        
        # Test health endpoint
        try:
            response = await self.client.get(f"{BASE_URL}/health")
            success = response.status_code == 200
            data = response.json() if success else {}
            await self.log_test("Health endpoint", success, 
                              f"DB: {data.get('database', 'unknown')}")
        except Exception as e:
            await self.log_test("Health endpoint", False, str(e))
    
    async def test_webhook_verification(self):
        """Test WhatsApp webhook verification."""
        print("\n🔍 Testing Webhook Verification...")
        
        # Test valid verification
        params = {
            "hub.mode": "subscribe",
            "hub.challenge": "test_challenge_123",
            "hub.verify_token": os.getenv("WHATSAPP_VERIFY_TOKEN", "mambo_verify_token")
        }
        
        try:
            response = await self.client.get(f"{BASE_URL}/webhook/whatsapp", params=params)
            success = response.status_code == 200 and response.text == "test_challenge_123"
            await self.log_test("Webhook verification (valid)", success, 
                              f"Response: {response.text}")
        except Exception as e:
            await self.log_test("Webhook verification (valid)", False, str(e))
        
        # Test invalid verification
        params["hub.verify_token"] = "wrong_token"
        try:
            response = await self.client.get(f"{BASE_URL}/webhook/whatsapp", params=params)
            success = response.status_code == 403
            await self.log_test("Webhook verification (invalid)", success, 
                              f"Status: {response.status_code}")
        except Exception as e:
            await self.log_test("Webhook verification (invalid)", False, str(e))
    
    async def test_message_processing(self):
        """Test message processing with sample WhatsApp payloads."""
        print("\n🔍 Testing Message Processing...")
        
        # Sample onboarding message (new user)
        onboarding_payload = {
            "entry": [{
                "changes": [{
                    "field": "messages",
                    "value": {
                        "messages": [{
                            "from": TEST_PHONE,
                            "type": "text",
                            "text": {"body": "Hello"}
                        }]
                    }
                }]
            }]
        }
        
        try:
            response = await self.client.post(
                f"{BASE_URL}/webhook/whatsapp",
                json=onboarding_payload,
                headers={"Content-Type": "application/json"}
            )
            success = response.status_code == 200
            await self.log_test("Message processing (onboarding)", success, 
                              f"Status: {response.status_code}")
        except Exception as e:
            await self.log_test("Message processing (onboarding)", False, str(e))
        
        # Sample meal request message
        meal_request_payload = {
            "entry": [{
                "changes": [{
                    "field": "messages",
                    "value": {
                        "messages": [{
                            "from": TEST_PHONE,
                            "type": "text",
                            "text": {"body": "What should I cook for dinner?"}
                        }]
                    }
                }]
            }]
        }
        
        try:
            response = await self.client.post(
                f"{BASE_URL}/webhook/whatsapp",
                json=meal_request_payload,
                headers={"Content-Type": "application/json"}
            )
            success = response.status_code == 200
            await self.log_test("Message processing (meal request)", success, 
                              f"Status: {response.status_code}")
        except Exception as e:
            await self.log_test("Message processing (meal request)", False, str(e))
    
    async def test_intent_classification(self):
        """Test intent classification with various messages."""
        print("\n🔍 Testing Intent Classification...")
        
        from app.services.intent_classifier import IntentClassifier
        classifier = IntentClassifier()
        
        test_cases = [
            ("What should I eat for dinner?", "WHATSDINNER"),
            ("How to make butter chicken?", "RECIPE_REQUEST"),
            ("I have rice and vegetables, what can I make?", "PANTRY_HELP"),
            ("Plan my meals for this week", "PLANWEEK"),
            ("I'm craving something spicy", "MOOD"),
            ("Do you have vegan options?", "DIETARY_QUERY"),
            ("Random text here", "OTHER")
        ]
        
        for message, expected_intent in test_cases:
            try:
                result = await classifier.classify_intent(message)
                success = result == expected_intent
                await self.log_test(f"Intent: '{message[:30]}...'", success, 
                                  f"Got: {result}, Expected: {expected_intent}")
            except Exception as e:
                await self.log_test(f"Intent: '{message[:30]}...'", False, str(e))
    
    async def test_database_operations(self):
        """Test database operations."""
        print("\n🔍 Testing Database Operations...")
        
        from app.services.user_service import UserService
        from app.services.meal_service import MealService
        
        user_service = UserService()
        meal_service = MealService()
        
        # Test user creation
        try:
            user = await user_service.create_user(TEST_PHONE, "Test User")
            success = user is not None
            await self.log_test("User creation", success, 
                              f"User ID: {user.get('id') if user else 'None'}")
        except Exception as e:
            await self.log_test("User creation", False, str(e))
        
        # Test meal search
        try:
            meals = await meal_service.search_meals("chicken", {"diet": "both"})
            success = isinstance(meals, list)
            await self.log_test("Meal search", success, 
                              f"Found {len(meals)} meals")
        except Exception as e:
            await self.log_test("Meal search", False, str(e))
        
        # Test meal population
        try:
            result = await meal_service.populate_indian_meals()
            success = result is True
            await self.log_test("Meal population", success, 
                              f"Population result: {result}")
        except Exception as e:
            await self.log_test("Meal population", False, str(e))
    
    async def test_image_processing(self):
        """Test image processing capabilities."""
        print("\n🔍 Testing Image Processing...")
        
        from app.services.image_service import ImageService
        image_service = ImageService()
        
        # Test fallback ingredients
        try:
            ingredients = image_service._fallback_ingredients()
            success = len(ingredients) > 0
            await self.log_test("Image fallback ingredients", success, 
                              f"Got {len(ingredients)} ingredients")
        except Exception as e:
            await self.log_test("Image fallback ingredients", False, str(e))
        
        # Test ingredient suggestions
        try:
            suggestions = await image_service.get_ingredient_suggestions(
                ["tomato", "onion", "chicken"]
            )
            success = "suggestions" in suggestions
            await self.log_test("Ingredient suggestions", success, 
                              f"Got {len(suggestions.get('suggestions', []))} suggestions")
        except Exception as e:
            await self.log_test("Ingredient suggestions", False, str(e))
    
    async def run_all_tests(self):
        """Run all tests."""
        print("🧪 Starting Mambo Bot Test Suite...")
        print(f"Testing against: {BASE_URL}")
        
        await self.test_health_endpoints()
        await self.test_webhook_verification()
        await self.test_message_processing()
        await self.test_intent_classification()
        await self.test_database_operations()
        await self.test_image_processing()
        
        # Summary
        print("\n📊 Test Summary:")
        passed = sum(1 for result in self.test_results if result["success"])
        total = len(self.test_results)
        print(f"Passed: {passed}/{total}")
        
        if passed < total:
            print("\n❌ Failed Tests:")
            for result in self.test_results:
                if not result["success"]:
                    print(f"  - {result['test']}: {result['details']}")
        
        await self.client.aclose()
        return passed == total

async def main():
    """Run the test suite."""
    tester = MamboBotTester()
    success = await tester.run_all_tests()
    
    if success:
        print("\n🎉 All tests passed! Your Mambo Bot is ready to go!")
    else:
        print("\n⚠️ Some tests failed. Check the details above.")
    
    return success

if __name__ == "__main__":
    asyncio.run(main())