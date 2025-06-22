import OpenAI from "openai";
import type { Profile } from "@shared/schema";

// the newest OpenAI model is "gpt-4o" which was released May 13, 2024. do not change this unless explicitly requested by the user
const openai = new OpenAI({ 
  apiKey: process.env.OPENAI_API_KEY || process.env.OPENAI_API_KEY_ENV_VAR || "default_key" 
});

interface MealPlanRequest {
  profiles: Profile[];
  householdSize: number;
  weekStartDate: string;
  dietaryRestrictions: string[];
  availableIngredients?: string[];
}

interface GeneratedMeal {
  name: string;
  description: string;
  mealType: "breakfast" | "lunch" | "dinner";
  dayOfWeek: number;
  calories: number;
  imageUrl: string;
  ingredients: any[];
  instructions: string;
}

interface MealPlanResponse {
  meals: GeneratedMeal[];
  weekStartDate: string;
  totalCalories: number;
  nutritionSummary: {
    protein: number;
    carbs: number;
    fat: number;
    fiber: number;
  };
}

interface AIInsight {
  type: "nutrition" | "shopping" | "leftover" | "budget";
  title: string;
  message: string;
  priority: "low" | "medium" | "high";
  icon: string;
}

export async function generateMealPlan(request: MealPlanRequest): Promise<MealPlanResponse> {
  const prompt = `Generate a weekly meal plan for a household with ${request.householdSize} members.

Household Profiles:
${request.profiles.map(profile => `
- Age: ${profile.age}, Daily Calories: ${profile.dailyCalories}, Diet: ${profile.dietType}
- Goal: ${profile.goal}
- Restrictions: ${profile.restrictions?.join(", ") || "None"}
- Preferences: ${profile.preferences?.join(", ") || "None"}
`).join("")}

Additional Requirements:
- Week starting: ${request.weekStartDate}
- Overall dietary restrictions: ${request.dietaryRestrictions.join(", ")}
${request.availableIngredients ? `- Available ingredients: ${request.availableIngredients.join(", ")}` : ""}

Generate 21 meals (7 days × 3 meals per day) that:
1. Meet the nutritional needs of all household members
2. Respect all dietary restrictions and preferences
3. Provide variety and balanced nutrition
4. Include realistic portions and calorie counts
5. Use seasonal and available ingredients

For each meal, provide:
- name: Clear, appealing meal name
- description: Brief description highlighting key ingredients
- mealType: "breakfast", "lunch", or "dinner"
- dayOfWeek: 0-6 (Monday = 0)
- calories: Estimated calories per serving
- imageUrl: Unsplash URL for a high-quality food photo
- ingredients: Array of ingredients with quantities
- instructions: Step-by-step cooking instructions

Also provide nutritionSummary with weekly totals for protein, carbs, fat, and fiber.

Respond with valid JSON in this exact format:
{
  "meals": [...],
  "weekStartDate": "${request.weekStartDate}",
  "totalCalories": number,
  "nutritionSummary": {
    "protein": number,
    "carbs": number,
    "fat": number,
    "fiber": number
  }
}`;

  try {
    const response = await openai.chat.completions.create({
      model: "gpt-4o",
      messages: [
        {
          role: "system",
          content: "You are a professional nutritionist and meal planning expert. Generate comprehensive, family-friendly meal plans that balance nutrition, taste, and dietary requirements."
        },
        {
          role: "user",
          content: prompt
        }
      ],
      response_format: { type: "json_object" },
      temperature: 0.7,
      max_tokens: 4000,
    });

    const result = JSON.parse(response.choices[0].message.content || "{}");
    return result as MealPlanResponse;
  } catch (error) {
    console.error("Error generating meal plan:", error);
    throw new Error("Failed to generate meal plan. Please try again.");
  }
}

export async function generateAIInsights(data: {
  inventoryItems: any[];
  expenses: any[];
  profiles: Profile[];
  recentMeals: any[];
  weeklyBudget?: number;
}): Promise<AIInsight[]> {
  const prompt = `Analyze this household's food and nutrition data to generate helpful AI insights.

Inventory Items: ${JSON.stringify(data.inventoryItems.slice(0, 10))}
Recent Expenses: ${JSON.stringify(data.expenses.slice(0, 10))}
Household Profiles: ${JSON.stringify(data.profiles.map(p => ({
  age: p.age,
  dailyCalories: p.dailyCalories,
  dietType: p.dietType,
  goal: p.goal,
  restrictions: p.restrictions,
  preferences: p.preferences
})))}
Recent Meals: ${JSON.stringify(data.recentMeals.slice(0, 5))}
Weekly Budget: ${data.weeklyBudget || "Not set"}

Generate 3-5 actionable insights that help the household with:
1. Smart shopping suggestions based on low stock items
2. Nutrition tips based on profile goals and recent meals
3. Leftover management and food waste reduction
4. Budget optimization and expense tracking
5. Dietary improvement recommendations

Each insight should have:
- type: "nutrition" | "shopping" | "leftover" | "budget"
- title: Short, clear title
- message: Helpful, actionable message
- priority: "low" | "medium" | "high"
- icon: Font Awesome icon class (like "fas fa-lightbulb")

Respond with valid JSON in this format:
{
  "insights": [
    {
      "type": "nutrition",
      "title": "Example Title",
      "message": "Example actionable message",
      "priority": "medium",
      "icon": "fas fa-leaf"
    }
  ]
}`;

  try {
    const response = await openai.chat.completions.create({
      model: "gpt-4o",
      messages: [
        {
          role: "system",
          content: "You are an AI nutritionist and household management expert. Provide practical, personalized insights to help families eat better and manage their kitchen more efficiently."
        },
        {
          role: "user",
          content: prompt
        }
      ],
      response_format: { type: "json_object" },
      temperature: 0.8,
      max_tokens: 1500,
    });

    const result = JSON.parse(response.choices[0].message.content || "{}");
    return result.insights || [];
  } catch (error) {
    console.error("Error generating AI insights:", error);
    return [];
  }
}

export async function analyzeReceipt(receiptText: string): Promise<{
  items: Array<{
    name: string;
    quantity: string;
    price: number;
    category: string;
  }>;
  total: number;
  store: string;
  date: string;
}> {
  const prompt = `Analyze this grocery receipt text and extract structured data:

${receiptText}

Extract:
1. Individual items with names, quantities, and prices
2. Total amount spent
3. Store name
4. Purchase date
5. Categorize each item (Fresh Produce, Dairy, Meat, Grains, etc.)

Respond with valid JSON in this format:
{
  "items": [
    {
      "name": "Item name",
      "quantity": "2 lbs" or "1 unit",
      "price": 3.99,
      "category": "Fresh Produce"
    }
  ],
  "total": 45.67,
  "store": "Store Name",
  "date": "2023-12-15"
}`;

  try {
    const response = await openai.chat.completions.create({
      model: "gpt-4o",
      messages: [
        {
          role: "system",
          content: "You are an expert at reading and parsing grocery receipts. Extract accurate item information, prices, and categorize items appropriately."
        },
        {
          role: "user",
          content: prompt
        }
      ],
      response_format: { type: "json_object" },
      temperature: 0.3,
      max_tokens: 2000,
    });

    const result = JSON.parse(response.choices[0].message.content || "{}");
    return result;
  } catch (error) {
    console.error("Error analyzing receipt:", error);
    throw new Error("Failed to analyze receipt. Please try again.");
  }
}
