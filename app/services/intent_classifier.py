"""
Intent classification service using keyword rules and OpenAI fallback.
"""

import re
from typing import List, Optional
from openai import OpenAI
from app.config.settings import settings

# the newest OpenAI model is "gpt-5" which was released August 7, 2025.
# do not change this unless explicitly requested by the user


class IntentClassifier:
    def __init__(self):
        self.openai_client = (
            OpenAI(api_key=settings.openai_api_key) if settings.openai_api_key else None
        )

        # Precise keyword rules with reduced overlap and false positives
        self.intent_keywords = {
            "RECIPE_REQUEST": [
                "recipe for",
                "how to make",
                "how do I cook",
                "how to prepare",
                "cooking method",
                "cooking steps",
                "preparation steps",
                "ingredients needed for",
                "cooking time for",
                "cooking instructions for",
            ],
            "PANTRY_HELP": [
                "what can I make with",
                "using these ingredients",
                "I have.*what can I",
                "use up these",
                "leftover.*what to",
                "ingredients at home",
                "with what I have",
                "from my pantry",
                "available ingredients.*make",
            ],
            "DIETARY_QUERY": [
                "vegan option",
                "vegetarian option",
                "gluten free",
                "dairy free",
                "low carb",
                "keto friendly",
                "healthy option",
                "diet food",
                "low calorie",
                "sugar free",
                "allergy free",
                "without dairy",
                "substitute for",
                "avoid.*because",
            ],
            "PLANWEEK": [
                "plan my week",
                "weekly plan",
                "meal plan",
                "weekly meal plan",
                "plan meals for week",
                "week meal plan",
                "7 day plan",
                "weekly menu",
                "meal planning",
                "plan ahead",
                "weekly cooking",
                "menu planning",
                "plan food for week",
                "organize weekly meals",
                "meal schedule",
                "weekly schedule",
            ],
            "UPLOAD_IMAGE": [
                "send photo",
                "upload image",
                "picture of food",
                "food photo",
                "recognize this",
                "identify this",
                "scan this",
                "check this image",
                "what's in this picture",
                "analyze photo",
                "image recognition",
            ],
            "MOOD": [
                "in the mood for",
                "craving something",
                "fancy something",
                "feel like eating",
                "want something spicy",
                "want something sweet",
                "craving",
                "feeling like",
                "dying for",
                "really want something",
                "comfort food",
                "something filling",
                "something light",
            ],
            "WHATSDINNER": [
                "what should I eat",
                "meal suggestion",
                "suggest meal",
                "dinner ideas",
                "food suggestions",
                "what should I cook",
                "suggest something to eat",
                "recommend meal",
                "food idea",
                "cooking ideas",
                "meal ideas",
                "what for dinner",
                "what for lunch",
                "what for breakfast",
                "cook something",
                "make something to eat",
                "prepare food",
                "cooking inspiration",
                "kitchen help",
                "food help",
            ],
            "ONBOARDING": [
                "getting started",
                "how to use",
                "setup preferences",
                "configure profile",
                "reset preferences",
                "change settings",
                "update profile",
                "help me start",
                "how does this work",
            ],
        }

    async def classify_intent(self, text: str) -> str:
        """Classify user intent using pattern-first approach with OpenAI fallback."""
        text_lower = text.lower().strip()

        # 1. Pattern-based disambiguation first (highest precision)
        pattern_intent = self._pattern_match(text_lower)
        if pattern_intent:
            return pattern_intent

        # 2. Precise keyword matching with word boundaries
        keyword_intent = self._precise_keyword_match(text_lower)
        if keyword_intent:
            return keyword_intent

        # 3. Hindi/Hinglish pattern matching
        hinglish_intent = self._hinglish_pattern_match(text_lower)
        if hinglish_intent:
            return hinglish_intent

        # 4. Fuzzy matching for typos and variations
        fuzzy_intent = self._fuzzy_keyword_match(text_lower)
        if fuzzy_intent:
            return fuzzy_intent

        # 5. If no match and OpenAI is available, use LLM fallback
        if self.openai_client:
            return await self._classify_with_openai(text)

        # Default to OTHER if no match and no OpenAI
        return "OTHER"

    def _precise_keyword_match(self, text: str) -> Optional[str]:
        """Precise keyword matching using regex word boundaries."""
        import re

        for intent, keywords in self.intent_keywords.items():
            for keyword in keywords:
                # Use regex for more precise matching
                if ".*" in keyword:
                    # Handle regex patterns in keywords
                    if re.search(keyword, text):
                        return intent
                else:
                    # Use word boundaries for exact phrases
                    pattern = r"\b" + re.escape(keyword) + r"\b"
                    if re.search(pattern, text):
                        return intent
        return None

    def _fuzzy_keyword_match(self, text: str) -> Optional[str]:
        """Fuzzy matching for common variations and typos."""
        # Common variations and typos
        fuzzy_patterns = {
            "WHATSDINNER": [
                "wat to eat",
                "wat should i eat",
                "food suggest",
                "meal suggest",
                "wat to cook",
                "wat for dinner",
                "dinner suggest",
                "food idea",
            ],
            "MOOD": [
                "want spicy",
                "want sweet",
                "craving spic",
                "want hot food",
                "feel like eating",
                "mood for",
                "fancy eating",
            ],
            "PLANWEEK": ["plan week", "week plan", "meal plan week", "weekly food"],
        }

        for intent, patterns in fuzzy_patterns.items():
            for pattern in patterns:
                if pattern in text:
                    return intent
        return None

    def _pattern_match(self, text: str) -> Optional[str]:
        """Advanced pattern-based matching using regex for complex queries."""
        import re

        # Recipe instruction patterns (highest priority)
        recipe_patterns = [
            r"\bhow\s+(to|do)\s+(make|cook|prepare)\s+",
            r"\brecipe\s+for\s+",
            r"\bsteps\s+to\s+(make|cook|prepare)\s+",
            r"\bcooking\s+(method|instructions)\s+for\s+",
        ]
        for pattern in recipe_patterns:
            if re.search(pattern, text):
                return "RECIPE_REQUEST"

        # Pantry/ingredient-based queries
        pantry_patterns = [
            r"\bwhat\s+can\s+i\s+(make|cook)\s+with\s+",
            r"\bi\s+have\s+.*?\s+(what|kya)\s+can\s+i\s+(make|cook)",
            r"\bwith\s+these\s+(ingredients|items)\s+",
            r"\buse\s+up\s+(these|leftover|remaining)\s+",
            r"\bfrom\s+my\s+(pantry|fridge|kitchen)\s+",
        ]
        for pattern in pantry_patterns:
            if re.search(pattern, text):
                return "PANTRY_HELP"

        # Meal timing with request context
        meal_request_patterns = [
            r"\bwhat\s+(should|can)\s+i\s+(eat|cook|make)\s+for\s+(breakfast|lunch|dinner)",
            r"\b(breakfast|lunch|dinner)\s+(idea|suggestion|option)",
            r"\bwhat\s+for\s+(breakfast|lunch|dinner)",
        ]
        for pattern in meal_request_patterns:
            if re.search(pattern, text):
                return "WHATSDINNER"

        # Dietary restriction patterns
        diet_patterns = [
            r"\b(without|no|avoid|skip)\s+(dairy|gluten|meat|eggs)",
            r"\b(vegan|vegetarian|keto|low.carb)\s+(option|meal|food)",
            r"\ballergy.free\s+",
            r"\bsubstitute\s+for\s+",
        ]
        for pattern in diet_patterns:
            if re.search(pattern, text):
                return "DIETARY_QUERY"

        # Image/photo patterns
        image_patterns = [
            r"\bsend\s+(photo|picture|image)",
            r"\bupload\s+(photo|picture|image)",
            r"\bcheck\s+this\s+(photo|picture|image)",
            r"\bwhat.s\s+in\s+this\s+(photo|picture|image)",
        ]
        for pattern in image_patterns:
            if re.search(pattern, text):
                return "UPLOAD_IMAGE"

        return None

    def _hinglish_pattern_match(self, text: str) -> Optional[str]:
        """Pattern matching for Hindi/Hinglish expressions."""
        import re

        # Hindi/Hinglish meal request patterns
        hinglish_meal_patterns = [
            r"\b(aaj|aj)\s+(kya|kya)\s+(banau|banau|pakau|khana)",
            r"\b(kya|kya)\s+(banau|pakau|khana)\s+(banau|banana|hai)",
            r"\b(khane|khaane)\s+(mein|me)\s+(kya|kya)",
            r"\b(nashta|breakfast)\s+(mein|me)\s+(kya|kya)",
            r"\b(dinner|lunch)\s+(mein|me)\s+(kya|kya)\s+(banau|khau)",
            r"\bkuch\s+(suggest|bata|batao|karo)\s+",
            r"\bmere\s+paas\s+.*?\s+(hai|he)\s+.*?(kya|kya)\s+(banau|bana)",
        ]
        for pattern in hinglish_meal_patterns:
            if re.search(pattern, text):
                return "WHATSDINNER"

        # Hindi pantry help patterns
        hinglish_pantry_patterns = [
            r"\bmere\s+paas\s+.*?\s+(hai|he)\s+.*?(kya|kya)\s+(bana|banau)",
            r"\b.*?\s+se\s+(kya|kya)\s+(bana|banau)\s+(sakta|sakti)",
            r"\byeh\s+ingredients\s+se\s+(kya|kya)\s+(bana|banau)",
        ]
        for pattern in hinglish_pantry_patterns:
            if re.search(pattern, text):
                return "PANTRY_HELP"

        # Hindi recipe request patterns
        hinglish_recipe_patterns = [
            r"\b(kaise|kese)\s+(banate|banaye|banau)\s+(hai|he)",
            r"\b.*?\s+(banane\s+ka|ka)\s+(tarika|method)",
            r"\brecipe\s+(batao|bata|kya)\s+hai",
        ]
        for pattern in hinglish_recipe_patterns:
            if re.search(pattern, text):
                return "RECIPE_REQUEST"

        return None

    async def _classify_with_openai(self, text: str) -> str:
        """Use OpenAI for intent classification fallback."""
        if not self.openai_client:
            return "OTHER"

        try:
            response = self.openai_client.chat.completions.create(
                model="gpt-5",
                messages=[
                    {
                        "role": "system",
                        "content": "You are an intent classifier for a meal planning WhatsApp bot called Mambo. "
                        "Classify the user's message into one of these intents:\n"
                        "- WHATSDINNER: General meal suggestions, recipe ideas, what to cook\n"
                        "- PLANWEEK: Weekly meal planning, meal schedule requests\n"
                        "- UPLOAD_IMAGE: Image recognition, ingredient identification\n"
                        "- MOOD: Cravings, taste preferences, comfort food requests\n"
                        "- RECIPE_REQUEST: Specific recipe instructions, cooking methods\n"
                        "- PANTRY_HELP: Using available ingredients, leftover management\n"
                        "- DIETARY_QUERY: Diet restrictions, allergy-free options\n"
                        "- ONBOARDING: Setup, preferences, help requests\n"
                        "- OTHER: Anything else\n\n"
                        "Return only the intent name.",
                    },
                    {"role": "user", "content": text},
                ],
            )

            intent = (
                response.choices[0].message.content.strip().upper()
                if response.choices[0].message.content
                else "OTHER"
            )
            valid_intents = [
                "WHATSDINNER",
                "PLANWEEK",
                "UPLOAD_IMAGE",
                "MOOD",
                "RECIPE_REQUEST",
                "PANTRY_HELP",
                "DIETARY_QUERY",
                "ONBOARDING",
                "OTHER",
            ]

            return intent if intent in valid_intents else "OTHER"

        except Exception as e:
            print(f"Error classifying intent with OpenAI: {e}")
            return "OTHER"
