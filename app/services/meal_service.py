"""
Meal service for database operations using Supabase.
"""

from typing import Optional, List, Dict, Any
from datetime import datetime
from app.config.supabase import supabase_client


class MealService:
    def __init__(self):
        self.client = supabase_client.client
        if self.client is None:
            print(
                "⚠️ Warning: Supabase client not available. Meal operations will fail."
            )

    async def create_meal(self, meal_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Create a new meal in the database."""
        if self.client is None:
            print("❌ Supabase client not available")
            return None

        try:
            response = self.client.table("meals").insert(meal_data).select().execute()
            return response.data[0] if response.data else None
        except Exception as e:
            print(f"Error creating meal: {e}")
            return None

    async def get_meals_by_cuisine(self, cuisine: str) -> List[Dict[str, Any]]:
        """Get all meals for a specific cuisine."""
        if self.client is None:
            print("❌ Supabase client not available")
            return []

        try:
            response = (
                self.client.table("meals").select("*").eq("cuisine", cuisine).execute()
            )
            return response.data if response.data else []
        except Exception as e:
            print(f"Error getting meals by cuisine: {e}")
            return []

    async def get_meals_by_diet(self, diet_type: str) -> List[Dict[str, Any]]:
        """Get all meals for a specific diet type."""
        if self.client is None:
            print("❌ Supabase client not available")
            return []

        try:
            response = (
                self.client.table("meals")
                .select("*")
                .eq("diet_type", diet_type)
                .execute()
            )
            return response.data if response.data else []
        except Exception as e:
            print(f"Error getting meals by diet: {e}")
            return []

    async def search_meals(
        self, query: str, user_preferences: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """Search meals based on query and user preferences."""
        if self.client is None:
            print("❌ Supabase client not available")
            return []

        try:
            # Start with base query
            query_builder = self.client.table("meals").select("*")

            # Apply user preferences filters
            if user_preferences:
                if user_preferences.get("diet"):
                    diet = user_preferences["diet"]
                    if diet == "veg":
                        query_builder = query_builder.eq("diet_type", "veg")
                    elif diet == "non-veg":
                        query_builder = query_builder.eq("diet_type", "non-veg")
                    # 'both' doesn't need filtering

                if user_preferences.get("cuisine_pref"):
                    cuisine = user_preferences["cuisine_pref"]
                    if cuisine != "surprise":
                        query_builder = query_builder.eq("cuisine", cuisine)

            # Execute query
            response = query_builder.execute()
            meals = response.data if response.data else []

            # Filter by query string if provided
            if query:
                query_lower = query.lower()
                filtered_meals = []
                for meal in meals:
                    # Search in name, ingredients, and tags
                    if (
                        query_lower in meal["name"].lower()
                        or any(
                            query_lower in ingredient.lower()
                            for ingredient in meal.get("ingredients", [])
                        )
                        or any(
                            query_lower in tag.lower() for tag in meal.get("tags", [])
                        )
                    ):
                        filtered_meals.append(meal)
                return filtered_meals

            return meals
        except Exception as e:
            print(f"Error searching meals: {e}")
            return []

    async def populate_indian_meals(self) -> bool:
        """Populate database with Indian meal options."""
        if self.client is None:
            print("❌ Supabase client not available")
            return False

        indian_meals = [
            # North Indian dishes
            {
                "name": "Butter Chicken",
                "cuisine": "north_indian",
                "ingredients": [
                    "chicken",
                    "tomato",
                    "cream",
                    "butter",
                    "garam masala",
                    "onion",
                    "garlic",
                    "ginger",
                ],
                "tags": ["popular", "creamy", "mild", "restaurant-style"],
                "recipe_text": "Marinate chicken in yogurt and spices. Cook in rich tomato-cream sauce with aromatic spices.",
                "estimated_time_min": 45,
                "diet_type": "non-veg",
            },
            {
                "name": "Dal Makhani",
                "cuisine": "north_indian",
                "ingredients": [
                    "black lentils",
                    "kidney beans",
                    "cream",
                    "butter",
                    "tomato",
                    "onion",
                    "garlic",
                    "ginger",
                ],
                "tags": ["comfort", "creamy", "rich", "vegetarian"],
                "recipe_text": "Slow-cooked black lentils and kidney beans in rich tomato-cream gravy.",
                "estimated_time_min": 60,
                "diet_type": "veg",
            },
            {
                "name": "Chicken Biryani",
                "cuisine": "north_indian",
                "ingredients": [
                    "basmati rice",
                    "chicken",
                    "yogurt",
                    "saffron",
                    "fried onions",
                    "mint",
                    "spices",
                ],
                "tags": ["festive", "aromatic", "one-pot", "special"],
                "recipe_text": "Layered rice and marinated chicken cooked with aromatic spices and saffron.",
                "estimated_time_min": 90,
                "diet_type": "non-veg",
            },
            {
                "name": "Palak Paneer",
                "cuisine": "north_indian",
                "ingredients": [
                    "spinach",
                    "paneer",
                    "onion",
                    "tomato",
                    "cream",
                    "garlic",
                    "ginger",
                    "spices",
                ],
                "tags": ["healthy", "green", "vegetarian", "protein-rich"],
                "recipe_text": "Fresh spinach curry with soft paneer cubes in aromatic spice blend.",
                "estimated_time_min": 30,
                "diet_type": "veg",
            },
            # South Indian dishes
            {
                "name": "Masala Dosa",
                "cuisine": "south_indian",
                "ingredients": [
                    "rice",
                    "urad dal",
                    "potato",
                    "onion",
                    "mustard seeds",
                    "curry leaves",
                    "coconut chutney",
                ],
                "tags": ["crispy", "breakfast", "fermented", "classic"],
                "recipe_text": "Crispy fermented crepe filled with spiced potato curry, served with chutney and sambar.",
                "estimated_time_min": 20,
                "diet_type": "veg",
            },
            {
                "name": "Sambar",
                "cuisine": "south_indian",
                "ingredients": [
                    "toor dal",
                    "tamarind",
                    "drumstick",
                    "okra",
                    "onion",
                    "tomato",
                    "sambar powder",
                ],
                "tags": ["tangy", "comfort", "nutritious", "traditional"],
                "recipe_text": "Tangy lentil curry with vegetables and tamarind, flavored with sambar powder.",
                "estimated_time_min": 40,
                "diet_type": "veg",
            },
            {
                "name": "Idli",
                "cuisine": "south_indian",
                "ingredients": [
                    "rice",
                    "urad dal",
                    "fenugreek seeds",
                    "coconut chutney",
                    "sambar",
                ],
                "tags": ["steamed", "healthy", "breakfast", "light"],
                "recipe_text": "Soft steamed rice cakes made from fermented batter, served with chutney and sambar.",
                "estimated_time_min": 15,
                "diet_type": "veg",
            },
            {
                "name": "Fish Curry",
                "cuisine": "south_indian",
                "ingredients": [
                    "fish",
                    "coconut",
                    "tamarind",
                    "curry leaves",
                    "mustard seeds",
                    "red chili",
                    "turmeric",
                ],
                "tags": ["coastal", "spicy", "coconut-based", "traditional"],
                "recipe_text": "Tangy fish curry in coconut-based gravy with South Indian spices.",
                "estimated_time_min": 35,
                "diet_type": "non-veg",
            },
            # Punjabi dishes
            {
                "name": "Rajma",
                "cuisine": "punjabi",
                "ingredients": [
                    "kidney beans",
                    "onion",
                    "tomato",
                    "ginger",
                    "garlic",
                    "cumin",
                    "coriander",
                    "garam masala",
                ],
                "tags": ["protein-rich", "comfort", "spicy", "traditional"],
                "recipe_text": "Kidney beans cooked in spiced tomato-onion gravy, best served with rice.",
                "estimated_time_min": 50,
                "diet_type": "veg",
            },
            {
                "name": "Makki Ki Roti with Sarson Ka Saag",
                "cuisine": "punjabi",
                "ingredients": [
                    "corn flour",
                    "mustard greens",
                    "spinach",
                    "butter",
                    "jaggery",
                    "ginger",
                    "garlic",
                ],
                "tags": ["winter", "healthy", "traditional", "rustic"],
                "recipe_text": "Corn flour flatbread served with spiced mustard greens curry and butter.",
                "estimated_time_min": 60,
                "diet_type": "veg",
            },
            # Indo-Chinese dishes
            {
                "name": "Chili Chicken",
                "cuisine": "indo_chinese",
                "ingredients": [
                    "chicken",
                    "bell peppers",
                    "onion",
                    "soy sauce",
                    "chili sauce",
                    "garlic",
                    "ginger",
                ],
                "tags": ["spicy", "fusion", "quick", "street-food"],
                "recipe_text": "Crispy chicken pieces tossed in spicy indo-Chinese sauce with peppers.",
                "estimated_time_min": 25,
                "diet_type": "non-veg",
            },
            {
                "name": "Vegetable Fried Rice",
                "cuisine": "indo_chinese",
                "ingredients": [
                    "rice",
                    "mixed vegetables",
                    "soy sauce",
                    "spring onions",
                    "garlic",
                    "ginger",
                    "oil",
                ],
                "tags": ["quick", "colorful", "one-pot", "versatile"],
                "recipe_text": "Stir-fried rice with mixed vegetables and Indo-Chinese seasonings.",
                "estimated_time_min": 20,
                "diet_type": "veg",
            },
            # Gujarati dishes
            {
                "name": "Dhokla",
                "cuisine": "gujarati",
                "ingredients": [
                    "gram flour",
                    "yogurt",
                    "ginger",
                    "green chili",
                    "mustard seeds",
                    "curry leaves",
                ],
                "tags": ["steamed", "healthy", "snack", "light"],
                "recipe_text": "Soft and spongy steamed cake made from fermented gram flour batter.",
                "estimated_time_min": 30,
                "diet_type": "veg",
            },
            {
                "name": "Undhiyu",
                "cuisine": "gujarati",
                "ingredients": [
                    "mixed vegetables",
                    "purple yam",
                    "sweet potato",
                    "eggplant",
                    "coconut",
                    "peanuts",
                ],
                "tags": ["winter", "mixed-vegetables", "traditional", "festive"],
                "recipe_text": "Mixed vegetable curry with winter vegetables cooked in aromatic spices.",
                "estimated_time_min": 75,
                "diet_type": "veg",
            },
            # Bengali dishes
            {
                "name": "Fish Jhol",
                "cuisine": "bengali",
                "ingredients": [
                    "fish",
                    "potato",
                    "onion",
                    "tomato",
                    "turmeric",
                    "cumin",
                    "mustard oil",
                ],
                "tags": ["light", "traditional", "simple", "homestyle"],
                "recipe_text": "Light fish curry with potatoes in aromatic Bengali spices.",
                "estimated_time_min": 30,
                "diet_type": "non-veg",
            },
            {
                "name": "Shorshe Ilish",
                "cuisine": "bengali",
                "ingredients": [
                    "hilsa fish",
                    "mustard seeds",
                    "mustard oil",
                    "green chili",
                    "turmeric",
                ],
                "tags": ["traditional", "mustard", "special", "aromatic"],
                "recipe_text": "Hilsa fish cooked in mustard seed paste - a Bengali delicacy.",
                "estimated_time_min": 25,
                "diet_type": "non-veg",
            },
        ]

        try:
            # Check if meals already exist to avoid duplicates
            existing_response = self.client.table("meals").select("name").execute()
            existing_names = [meal["name"] for meal in (existing_response.data or [])]

            # Filter out meals that already exist
            new_meals = [
                meal for meal in indian_meals if meal["name"] not in existing_names
            ]

            if new_meals:
                response = self.client.table("meals").insert(new_meals).execute()
                if response.data:
                    print(
                        f"✅ Successfully added {len(new_meals)} Indian meals to database"
                    )
                    return True
                else:
                    print("❌ Failed to add meals - no data returned")
                    return False
            else:
                print("ℹ️ All Indian meals already exist in database")
                return True

        except Exception as e:
            print(f"❌ Error populating Indian meals: {e}")
            return False
