"""
Image processing service for ingredient detection using Google Cloud Vision API.
"""

import os
import json
from typing import List, Dict, Any, Optional
from google.cloud import vision
import tempfile
import httpx


class ImageService:
    def __init__(self):
        self.client = None
        self._initialize_vision_client()

    def _initialize_vision_client(self):
        """Initialize Google Cloud Vision client."""
        try:
            # Get credentials from environment
            credentials_json = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
            if not credentials_json:
                print("⚠️ Google Cloud Vision credentials not available")
                return

            # Parse JSON credentials
            credentials_dict = json.loads(credentials_json)

            # Create temporary file for credentials
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".json", delete=False
            ) as temp_file:
                json.dump(credentials_dict, temp_file)
                temp_file_path = temp_file.name

            # Set environment variable for Google client
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = temp_file_path

            # Initialize client
            self.client = vision.ImageAnnotatorClient()
            print("✅ Google Cloud Vision client initialized")

        except Exception as e:
            print(f"❌ Failed to initialize Google Cloud Vision: {e}")
            self.client = None

    async def detect_ingredients_from_url(self, image_url: str) -> List[str]:
        """Detect ingredients from an image URL."""
        if not self.client:
            return self._fallback_ingredients()

        try:
            # Download image
            async with httpx.AsyncClient() as http_client:
                response = await http_client.get(image_url)
                response.raise_for_status()
                image_content = response.content

            # Analyze image
            return await self._analyze_image_content(image_content)

        except Exception as e:
            print(f"Error detecting ingredients from URL: {e}")
            return self._fallback_ingredients()

    async def detect_ingredients_from_base64(self, image_base64: str) -> List[str]:
        """Detect ingredients from base64 encoded image."""
        if not self.client:
            return self._fallback_ingredients()

        try:
            import base64

            image_content = base64.b64decode(image_base64)
            return await self._analyze_image_content(image_content)

        except Exception as e:
            print(f"Error detecting ingredients from base64: {e}")
            return self._fallback_ingredients()

    async def _analyze_image_content(self, image_content: bytes) -> List[str]:
        """Analyze image content using Google Cloud Vision."""
        try:
            # Create image object
            image = vision.Image(content=image_content)

            # Perform label detection
            response = self.client.label_detection(image=image)
            labels = response.label_annotations

            # Perform object detection
            objects = self.client.object_localization(
                image=image
            ).localized_object_annotations

            # Extract potential ingredients
            detected_items = []

            # Process labels
            for label in labels:
                if label.score > 0.6:  # Only high-confidence labels
                    detected_items.append(label.description.lower())

            # Process objects
            for obj in objects:
                if obj.score > 0.5:  # Only high-confidence objects
                    detected_items.append(obj.name.lower())

            # Filter and map to common ingredients
            ingredients = self._filter_food_items(detected_items)

            if ingredients:
                print(f"✅ Detected ingredients: {ingredients}")
                return ingredients
            else:
                return self._fallback_ingredients()

        except Exception as e:
            print(f"Error analyzing image: {e}")
            return self._fallback_ingredients()

    def _filter_food_items(self, detected_items: List[str]) -> List[str]:
        """Filter detected items to extract likely food ingredients."""
        # Common food ingredient mappings
        food_mappings = {
            # Vegetables
            "vegetable": ["mixed vegetables"],
            "carrot": ["carrot", "carrots"],
            "potato": ["potato", "potatoes"],
            "onion": ["onion", "onions"],
            "tomato": ["tomato", "tomatoes"],
            "bell pepper": ["bell pepper", "capsicum"],
            "spinach": ["spinach", "greens"],
            "cabbage": ["cabbage"],
            "cauliflower": ["cauliflower"],
            "broccoli": ["broccoli"],
            "cucumber": ["cucumber"],
            "eggplant": ["eggplant", "brinjal"],
            "ginger": ["ginger"],
            "garlic": ["garlic"],
            "chili": ["chili", "pepper"],
            # Fruits
            "apple": ["apple", "apples"],
            "banana": ["banana", "bananas"],
            "orange": ["orange", "oranges"],
            "lemon": ["lemon", "lime"],
            "mango": ["mango"],
            # Proteins
            "chicken": ["chicken", "poultry"],
            "fish": ["fish", "seafood"],
            "egg": ["egg", "eggs"],
            "meat": ["meat", "beef", "mutton"],
            "shrimp": ["shrimp", "prawn"],
            # Grains & Legumes
            "rice": ["rice"],
            "wheat": ["wheat", "flour"],
            "bread": ["bread"],
            "pasta": ["pasta"],
            "beans": ["beans", "legumes"],
            "lentil": ["lentils", "dal"],
            "chickpea": ["chickpeas", "chana"],
            # Dairy
            "milk": ["milk"],
            "cheese": ["cheese", "paneer"],
            "yogurt": ["yogurt", "curd"],
            "butter": ["butter"],
            # Spices & Herbs
            "spice": ["spices"],
            "herb": ["herbs"],
            "cumin": ["cumin"],
            "coriander": ["coriander"],
            "turmeric": ["turmeric"],
            "mustard": ["mustard seeds"],
            # Oils & Condiments
            "oil": ["oil", "cooking oil"],
            "vinegar": ["vinegar"],
            "sauce": ["sauce"],
            "salt": ["salt"],
        }

        # Reverse mapping for easier lookup
        ingredient_keywords = {}
        for ingredient, keywords in food_mappings.items():
            for keyword in keywords:
                ingredient_keywords[keyword] = ingredient

        # Find matching ingredients
        found_ingredients = set()

        for item in detected_items:
            item_lower = item.lower()

            # Direct match
            if item_lower in ingredient_keywords:
                found_ingredients.add(ingredient_keywords[item_lower])
                continue

            # Partial match
            for keyword, ingredient in ingredient_keywords.items():
                if keyword in item_lower or item_lower in keyword:
                    found_ingredients.add(ingredient)
                    break

        return list(found_ingredients)

    def _fallback_ingredients(self) -> List[str]:
        """Fallback ingredients when detection fails."""
        return ["mixed vegetables", "onion", "tomato", "garlic", "spices"]

    async def get_ingredient_suggestions(
        self, detected_ingredients: List[str]
    ) -> Dict[str, Any]:
        """Get meal suggestions based on detected ingredients."""
        if not detected_ingredients:
            return {
                "ingredients": [],
                "suggestions": [],
                "message": "No ingredients detected. Could you tell me what ingredients you have?",
            }

        # Create ingredient-based suggestions
        suggestions = []

        # Basic categorization
        has_vegetables = any(
            ing in detected_ingredients
            for ing in [
                "carrot",
                "potato",
                "onion",
                "tomato",
                "spinach",
                "mixed vegetables",
            ]
        )
        has_protein = any(
            ing in detected_ingredients
            for ing in ["chicken", "fish", "egg", "meat", "paneer"]
        )
        has_grains = any(
            ing in detected_ingredients for ing in ["rice", "wheat", "bread", "pasta"]
        )

        # Generate suggestions based on available ingredients
        if has_vegetables and has_protein:
            suggestions.extend(
                [
                    "Vegetable curry with protein",
                    "Stir-fried vegetables with meat/fish",
                    "Mixed vegetable and protein rice bowl",
                ]
            )

        if has_vegetables and has_grains:
            suggestions.extend(
                [
                    "Vegetable fried rice",
                    "Vegetable pasta",
                    "Mixed vegetable curry with rice",
                ]
            )

        if has_protein and has_grains:
            suggestions.extend(
                ["Protein biryani", "Egg fried rice", "Chicken/fish curry with rice"]
            )

        if "potato" in detected_ingredients:
            suggestions.extend(
                ["Aloo (potato) curry", "Mashed potatoes", "Potato stir-fry"]
            )

        if "egg" in detected_ingredients:
            suggestions.extend(
                ["Scrambled eggs", "Egg curry", "Omelet with vegetables"]
            )

        # Ensure we have at least some suggestions
        if not suggestions:
            suggestions = [
                "Simple vegetable stir-fry",
                "Basic curry with available ingredients",
                "Mixed ingredient soup",
            ]

        return {
            "ingredients": detected_ingredients,
            "suggestions": suggestions[:5],  # Limit to top 5
            "message": f'I can see {", ".join(detected_ingredients)}. Here are some meal ideas:',
        }
