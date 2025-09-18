"""
Meal recommendation service using user preferences and intelligent filtering.
"""
import random
from typing import List, Dict, Any, Optional
from app.services.meal_service import MealService
from app.services.user_service import UserService
from app.services.intent_classifier import IntentClassifier

class RecommendationService:
    def __init__(self):
        self.meal_service = MealService()
        self.user_service = UserService()
        self.intent_classifier = IntentClassifier()
    
    async def get_meal_recommendations(self, whatsapp_id: str, user_message: str, max_results: int = 3) -> List[Dict[str, Any]]:
        """Get personalized meal recommendations based on user message and preferences."""
        try:
            # Get user preferences
            user = await self.user_service.get_user_by_whatsapp_id(whatsapp_id)
            if not user:
                return await self._get_default_recommendations()
            
            # Classify user intent
            intent = await self.intent_classifier.classify_intent(user_message)
            
            # Get recommendations based on intent and preferences
            recommendations = await self._generate_recommendations(user, user_message, intent, max_results)
            
            return recommendations
        except Exception as e:
            print(f"Error getting recommendations: {e}")
            return await self._get_default_recommendations()
    
    async def _generate_recommendations(self, user: Dict[str, Any], message: str, intent: str, max_results: int) -> List[Dict[str, Any]]:
        """Generate recommendations based on user preferences and intent."""
        # Build search criteria
        search_criteria = {
            'diet': user.get('diet'),
            'cuisine_pref': user.get('cuisine_pref'),
            'allergies': user.get('allergies', []),
            'household_size': user.get('household_size')
        }
        
        # Handle different intents
        if intent == "MOOD":
            return await self._handle_mood_request(message, search_criteria, max_results)
        elif intent == "RECIPE_REQUEST":
            return await self._handle_recipe_request(message, search_criteria, max_results)
        elif intent == "PANTRY_HELP":
            return await self._handle_pantry_request(message, search_criteria, max_results)
        elif intent == "DIETARY_QUERY":
            return await self._handle_dietary_request(message, search_criteria, max_results)
        elif intent == "PLANWEEK":
            return await self._handle_weekly_plan_request(search_criteria, max_results * 2)
        else:  # WHATSDINNER or OTHER
            return await self._handle_general_request(message, search_criteria, max_results)
    
    async def _handle_mood_request(self, message: str, criteria: Dict[str, Any], max_results: int) -> List[Dict[str, Any]]:
        """Handle mood-based requests (cravings, comfort food, etc.)."""
        message_lower = message.lower()
        
        # Mood-based tag mapping
        mood_tags = {
            'spicy': ['spicy', 'hot'],
            'comfort': ['comfort', 'creamy', 'rich'],
            'light': ['light', 'healthy', 'steamed'],
            'quick': ['quick', 'fast'],
            'sweet': ['sweet'],
            'filling': ['filling', 'heavy', 'protein-rich'],
            'healthy': ['healthy', 'nutritious'],
            'traditional': ['traditional', 'authentic', 'homestyle']
        }
        
        # Extract query based on mood indicators
        search_query = ""
        preferred_tags = []
        
        for mood, tags in mood_tags.items():
            if mood in message_lower:
                preferred_tags.extend(tags)
                search_query = mood
                break
        
        # Search meals with mood preferences
        meals = await self.meal_service.search_meals(search_query, criteria)
        
        # Prioritize meals with matching tags
        if preferred_tags:
            meals = self._prioritize_by_tags(meals, preferred_tags)
        
        return self._format_recommendations(meals[:max_results], f"Based on your mood for {search_query or 'comfort'} food")
    
    async def _handle_recipe_request(self, message: str, criteria: Dict[str, Any], max_results: int) -> List[Dict[str, Any]]:
        """Handle recipe-specific requests."""
        # Extract dish name from message
        message_lower = message.lower()
        
        # Common recipe request patterns
        if "recipe for" in message_lower:
            dish_name = message_lower.split("recipe for")[1].strip()
        elif "how to make" in message_lower:
            dish_name = message_lower.split("how to make")[1].strip()
        else:
            dish_name = message_lower
        
        # Clean up dish name
        dish_name = dish_name.replace("?", "").strip()
        
        # Search for specific dish or similar
        meals = await self.meal_service.search_meals(dish_name, criteria)
        
        return self._format_recommendations(meals[:max_results], f"Recipe suggestions for '{dish_name}'")
    
    async def _handle_pantry_request(self, message: str, criteria: Dict[str, Any], max_results: int) -> List[Dict[str, Any]]:
        """Handle pantry/ingredient-based requests."""
        # Extract ingredients from message
        ingredients = self._extract_ingredients_from_message(message)
        
        if not ingredients:
            return await self._handle_general_request(message, criteria, max_results)
        
        # Search meals that use these ingredients
        meals = await self.meal_service.search_meals("", criteria)
        
        # Filter meals that contain the mentioned ingredients
        matching_meals = []
        for meal in meals:
            meal_ingredients = [ing.lower() for ing in meal.get('ingredients', [])]
            if any(ingredient.lower() in ' '.join(meal_ingredients) for ingredient in ingredients):
                # Add a score based on ingredient matches
                meal['ingredient_match_score'] = sum(
                    1 for ingredient in ingredients 
                    if any(ingredient.lower() in meal_ing for meal_ing in meal_ingredients)
                )
                matching_meals.append(meal)
        
        # Sort by ingredient match score
        matching_meals.sort(key=lambda x: x.get('ingredient_match_score', 0), reverse=True)
        
        ingredients_text = ", ".join(ingredients)
        return self._format_recommendations(matching_meals[:max_results], f"Using your ingredients: {ingredients_text}")
    
    async def _handle_dietary_request(self, message: str, criteria: Dict[str, Any], max_results: int) -> List[Dict[str, Any]]:
        """Handle dietary restriction requests."""
        message_lower = message.lower()
        
        # Override criteria based on dietary request
        if 'vegan' in message_lower or 'plant based' in message_lower:
            criteria['diet'] = 'veg'
            dietary_filter = 'vegan'
        elif 'vegetarian' in message_lower:
            criteria['diet'] = 'veg'
            dietary_filter = 'vegetarian'
        elif 'low carb' in message_lower or 'keto' in message_lower:
            dietary_filter = 'low-carb'
        elif 'gluten free' in message_lower:
            dietary_filter = 'gluten-free'
        elif 'dairy free' in message_lower:
            dietary_filter = 'dairy-free'
        else:
            dietary_filter = 'healthy'
        
        meals = await self.meal_service.search_meals(dietary_filter, criteria)
        
        return self._format_recommendations(meals[:max_results], f"Meals for your {dietary_filter} preference")
    
    async def _handle_weekly_plan_request(self, criteria: Dict[str, Any], max_results: int) -> List[Dict[str, Any]]:
        """Handle weekly meal planning requests."""
        # Get diverse meals across different cuisines and types
        all_meals = await self.meal_service.search_meals("", criteria)
        
        if not all_meals:
            return await self._get_default_recommendations()
        
        # Create diverse weekly plan
        weekly_plan = self._create_diverse_weekly_plan(all_meals, max_results)
        
        return self._format_recommendations(weekly_plan, "Your weekly meal plan")
    
    async def _handle_general_request(self, message: str, criteria: Dict[str, Any], max_results: int) -> List[Dict[str, Any]]:
        """Handle general meal requests."""
        # Extract any specific food mentions from message
        query = self._extract_food_query(message)
        
        meals = await self.meal_service.search_meals(query, criteria)
        
        if not meals:
            return await self._get_default_recommendations()
        
        # Add variety by shuffling if we have enough meals
        if len(meals) > max_results:
            random.shuffle(meals)
        
        suggestion_text = f"Here are some meal suggestions" + (f" for {query}" if query else "")
        return self._format_recommendations(meals[:max_results], suggestion_text)
    
    def _extract_ingredients_from_message(self, message: str) -> List[str]:
        """Extract ingredient names from user message."""
        message_lower = message.lower()
        
        # Common ingredients to look for
        common_ingredients = [
            'chicken', 'fish', 'egg', 'eggs', 'paneer', 'potato', 'potatoes',
            'onion', 'onions', 'tomato', 'tomatoes', 'rice', 'dal', 'lentils',
            'spinach', 'cauliflower', 'beans', 'peas', 'carrot', 'carrots',
            'ginger', 'garlic', 'chili', 'pepper', 'coconut', 'yogurt',
            'bread', 'roti', 'chapati', 'milk', 'butter', 'oil'
        ]
        
        found_ingredients = []
        for ingredient in common_ingredients:
            if ingredient in message_lower:
                found_ingredients.append(ingredient)
        
        return found_ingredients
    
    def _extract_food_query(self, message: str) -> str:
        """Extract food-related query from message."""
        message_lower = message.lower()
        
        # Remove common question words and focus on food terms
        stop_words = ['what', 'should', 'can', 'i', 'eat', 'cook', 'make', 'for', 'suggest', 'recommend']
        words = message_lower.split()
        food_words = [word for word in words if word not in stop_words and len(word) > 2]
        
        return ' '.join(food_words[:3])  # Limit to first 3 relevant words
    
    def _prioritize_by_tags(self, meals: List[Dict[str, Any]], preferred_tags: List[str]) -> List[Dict[str, Any]]:
        """Prioritize meals that match preferred tags."""
        scored_meals = []
        
        for meal in meals:
            meal_tags = meal.get('tags', [])
            score = sum(1 for tag in preferred_tags if tag in meal_tags)
            meal['tag_score'] = score
            scored_meals.append(meal)
        
        # Sort by tag score, then randomly for variety
        scored_meals.sort(key=lambda x: (x.get('tag_score', 0), random.random()), reverse=True)
        return scored_meals
    
    def _create_diverse_weekly_plan(self, meals: List[Dict[str, Any]], num_days: int) -> List[Dict[str, Any]]:
        """Create a diverse weekly meal plan."""
        if not meals:
            return []
        
        # Group meals by cuisine for diversity
        cuisine_groups = {}
        for meal in meals:
            cuisine = meal.get('cuisine', 'other')
            if cuisine not in cuisine_groups:
                cuisine_groups[cuisine] = []
            cuisine_groups[cuisine].append(meal)
        
        # Select meals from different cuisines
        selected_meals = []
        cuisines = list(cuisine_groups.keys())
        
        for i in range(num_days):
            if cuisines:
                cuisine = cuisines[i % len(cuisines)]
                if cuisine_groups[cuisine]:
                    meal = random.choice(cuisine_groups[cuisine])
                    selected_meals.append(meal)
                    cuisine_groups[cuisine].remove(meal)  # Avoid duplicates
        
        return selected_meals
    
    def _format_recommendations(self, meals: List[Dict[str, Any]], context: str) -> List[Dict[str, Any]]:
        """Format meal recommendations with additional context."""
        formatted_recommendations = []
        
        for meal in meals:
            recommendation = {
                'name': meal.get('name'),
                'cuisine': meal.get('cuisine'),
                'diet_type': meal.get('diet_type'),
                'estimated_time_min': meal.get('estimated_time_min'),
                'ingredients': meal.get('ingredients', []),
                'tags': meal.get('tags', []),
                'recipe_text': meal.get('recipe_text'),
                'context': context
            }
            formatted_recommendations.append(recommendation)
        
        return formatted_recommendations
    
    async def _get_default_recommendations(self) -> List[Dict[str, Any]]:
        """Fallback recommendations when database is unavailable."""
        default_meals = [
            {
                'name': 'Dal Rice',
                'cuisine': 'indian',
                'diet_type': 'veg',
                'estimated_time_min': 30,
                'ingredients': ['dal', 'rice', 'turmeric', 'cumin'],
                'tags': ['comfort', 'healthy', 'simple'],
                'recipe_text': 'Simple comfort meal with lentils and rice',
                'context': 'Quick comfort food suggestion'
            },
            {
                'name': 'Vegetable Stir Fry',
                'cuisine': 'indo_chinese',
                'diet_type': 'veg',
                'estimated_time_min': 20,
                'ingredients': ['mixed vegetables', 'soy sauce', 'garlic'],
                'tags': ['quick', 'healthy', 'colorful'],
                'recipe_text': 'Quick stir-fried vegetables with Asian flavors',
                'context': 'Quick healthy meal suggestion'
            },
            {
                'name': 'Egg Curry',
                'cuisine': 'indian',
                'diet_type': 'non-veg',
                'estimated_time_min': 25,
                'ingredients': ['eggs', 'onion', 'tomato', 'spices'],
                'tags': ['protein-rich', 'comforting'],
                'recipe_text': 'Spiced egg curry with rich gravy',
                'context': 'Protein-rich meal suggestion'
            }
        ]
        
        return default_meals