# app/services/onboarding_service.py
from typing import Any, Dict, Optional
from datetime import datetime

VALID_DIETS = {"vegetarian", "vegan", "omnivore", "pescatarian", "keto", "other"}


class OnboardingService:
    """
    Handles onboarding steps. Each step MUST persist the user's selection using UserService.
    """

    def __init__(self, user_service):
        self.user_service = user_service

    def _resp(self, ok: bool, data: Any = None, error: Optional[str] = None):
        return {"ok": ok, "data": data, "error": error}

    def process_step(
        self, whatsapp_id: str, step: int, payload: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Main entry: process a numeric onboarding step (1..N) and persist.
        Example payloads per step:
          step 1: {"diet": "vegetarian"}
          step 2: {"cuisine_pref": ["Indian","Italian"]} or comma string
          step 3: {"allergies": ["peanut","gluten"]} or comma string
          step 4: {"household_size": 3}
        """
        if not whatsapp_id:
            return self._resp(False, None, "whatsapp_id required")

        handlers = {
            1: self.save_diet,
            2: self.save_cuisine_pref,
            3: self.save_allergies,
            4: self.save_household_size,
        }
        handler = handlers.get(step)
        if not handler:
            return self._resp(False, None, f"unsupported onboarding step {step}")

        return handler(whatsapp_id, payload)

    def save_diet(self, whatsapp_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        diet = payload.get("diet")
        if not diet:
            return self._resp(False, None, "diet missing in payload")
        diet_clean = str(diet).strip().lower()
        if diet_clean not in VALID_DIETS:
            # Accept unknown diets but mark as 'other' and store original
            store = {"diet": "other", "diet_raw": diet}
        else:
            store = {"diet": diet_clean}
        # Move onboarding forward
        store["onboarding_step"] = 1
        store["last_active"] = datetime.utcnow().isoformat()
        result = self.user_service.create_or_update_user(
            whatsapp_id=whatsapp_id, **store
        )
        return result

    def save_cuisine_pref(
        self, whatsapp_id: str, payload: Dict[str, Any]
    ) -> Dict[str, Any]:
        cuisines = payload.get("cuisine_pref") or payload.get("cuisines")
        if cuisines is None:
            return self._resp(False, None, "cuisine_pref missing")
        # Normalize: accept list or comma-separated string
        if isinstance(cuisines, str):
            cuisine_list = [c.strip() for c in cuisines.split(",") if c.strip()]
        elif isinstance(cuisines, (list, tuple)):
            cuisine_list = [str(c).strip() for c in cuisines if str(c).strip()]
        else:
            return self._resp(False, None, "unsupported cuisine_pref format")
        store = {
            "cuisine_pref": ",".join(cuisine_list),
            "onboarding_step": 2,
            "last_active": datetime.utcnow().isoformat(),
        }
        return self.user_service.create_or_update_user(whatsapp_id=whatsapp_id, **store)

    def save_allergies(
        self, whatsapp_id: str, payload: Dict[str, Any]
    ) -> Dict[str, Any]:
        allergies = payload.get("allergies")
        if allergies is None:
            return self._resp(False, None, "allergies missing")
        if isinstance(allergies, str):
            allergy_list = [a.strip() for a in allergies.split(",") if a.strip()]
        elif isinstance(allergies, (list, tuple)):
            allergy_list = [str(a).strip() for a in allergies if str(a).strip()]
        else:
            return self._resp(False, None, "unsupported allergies format")
        # store in the 'allergies' _text column as JSON-like string
        store = {
            "allergies": str(allergy_list),
            "onboarding_step": 3,
            "last_active": datetime.utcnow().isoformat(),
        }
        return self.user_service.create_or_update_user(whatsapp_id=whatsapp_id, **store)

    def save_household_size(
        self, whatsapp_id: str, payload: Dict[str, Any]
    ) -> Dict[str, Any]:
        size = payload.get("household_size")
        if size is None:
            return self._resp(False, None, "household_size missing")
        try:
            size_int = int(size)
        except Exception:
            return self._resp(False, None, "household_size must be an integer")
        store = {
            "household_size": str(size_int),
            "onboarding_step": 4,
            "last_active": datetime.utcnow().isoformat(),
        }
        return self.user_service.create_or_update_user(whatsapp_id=whatsapp_id, **store)
