import type { Express } from "express";
import { createServer, type Server } from "http";
import { storage } from "./storage";
import { setupAuth, isAuthenticated } from "./replitAuth";
import { generateMealPlan, generateAIInsights, analyzeReceipt } from "./services/openai";
import {
  insertHouseholdSchema,
  insertProfileSchema,
  insertInventoryItemSchema,
  insertMealPlanSchema,
  insertMealSchema,
  insertMealApprovalSchema,
  insertMealCommentSchema,
  insertShoppingListItemSchema,
  insertExpenseSchema,
} from "@shared/schema";

export async function registerRoutes(app: Express): Promise<Server> {
  // Auth middleware
  await setupAuth(app);

  // Auth routes
  app.get('/api/auth/user', isAuthenticated, async (req: any, res) => {
    try {
      const userId = req.user.claims.sub;
      const user = await storage.getUser(userId);
      
      // Auto-create a default household if user doesn't have one
      if (user) {
        const households = await storage.getUserHouseholds(userId);
        if (households.length === 0) {
          const defaultHousehold = await storage.createHousehold({
            name: `${user.firstName || 'My'} Household`,
            createdById: userId,
            weeklyBudget: '300.00',
          });
          
          await storage.addHouseholdMember({
            householdId: defaultHousehold.id,
            userId,
            role: "admin",
          });
        }
      }
      
      res.json(user);
    } catch (error) {
      console.error("Error fetching user:", error);
      res.status(500).json({ message: "Failed to fetch user" });
    }
  });

  // Household routes
  app.post('/api/households', isAuthenticated, async (req: any, res) => {
    try {
      const userId = req.user.claims.sub;
      const householdData = insertHouseholdSchema.parse({
        ...req.body,
        createdById: userId,
      });
      
      const household = await storage.createHousehold(householdData);
      
      // Add creator as admin member
      await storage.addHouseholdMember({
        householdId: household.id,
        userId,
        role: "admin",
      });
      
      res.json(household);
    } catch (error) {
      console.error("Error creating household:", error);
      res.status(500).json({ message: "Failed to create household" });
    }
  });

  app.get('/api/households', isAuthenticated, async (req: any, res) => {
    try {
      const userId = req.user.claims.sub;
      const households = await storage.getUserHouseholds(userId);
      res.json(households);
    } catch (error) {
      console.error("Error fetching households:", error);
      res.status(500).json({ message: "Failed to fetch households" });
    }
  });

  app.get('/api/households/:id', isAuthenticated, async (req: any, res) => {
    try {
      const householdId = parseInt(req.params.id);
      const household = await storage.getHousehold(householdId);
      
      if (!household) {
        return res.status(404).json({ message: "Household not found" });
      }
      
      res.json(household);
    } catch (error) {
      console.error("Error fetching household:", error);
      res.status(500).json({ message: "Failed to fetch household" });
    }
  });

  app.get('/api/households/:id/members', isAuthenticated, async (req: any, res) => {
    try {
      const householdId = parseInt(req.params.id);
      const members = await storage.getHouseholdMembers(householdId);
      res.json(members);
    } catch (error) {
      console.error("Error fetching household members:", error);
      res.status(500).json({ message: "Failed to fetch household members" });
    }
  });

  // Profile routes
  app.post('/api/profiles', isAuthenticated, async (req: any, res) => {
    try {
      const userId = req.user.claims.sub;
      const profileData = insertProfileSchema.parse({
        ...req.body,
        userId,
      });
      
      const profile = await storage.createProfile(profileData);
      res.json(profile);
    } catch (error) {
      console.error("Error creating profile:", error);
      res.status(500).json({ message: "Failed to create profile" });
    }
  });

  app.get('/api/households/:id/profiles', isAuthenticated, async (req: any, res) => {
    try {
      const householdId = parseInt(req.params.id);
      const profiles = await storage.getHouseholdProfiles(householdId);
      res.json(profiles);
    } catch (error) {
      console.error("Error fetching profiles:", error);
      res.status(500).json({ message: "Failed to fetch profiles" });
    }
  });

  app.get('/api/profiles/:householdId/me', isAuthenticated, async (req: any, res) => {
    try {
      const userId = req.user.claims.sub;
      const householdId = parseInt(req.params.householdId);
      const profile = await storage.getProfile(userId, householdId);
      res.json(profile);
    } catch (error) {
      console.error("Error fetching user profile:", error);
      res.status(500).json({ message: "Failed to fetch user profile" });
    }
  });

  app.put('/api/profiles/:householdId/me', isAuthenticated, async (req: any, res) => {
    try {
      const userId = req.user.claims.sub;
      const householdId = parseInt(req.params.householdId);
      const updates = req.body;
      
      const profile = await storage.updateProfile(userId, householdId, updates);
      res.json(profile);
    } catch (error) {
      console.error("Error updating profile:", error);
      res.status(500).json({ message: "Failed to update profile" });
    }
  });

  // Inventory routes
  app.post('/api/inventory', isAuthenticated, async (req: any, res) => {
    try {
      const userId = req.user.claims.sub;
      const itemData = insertInventoryItemSchema.parse({
        ...req.body,
        addedById: userId,
      });
      
      const item = await storage.createInventoryItem(itemData);
      res.json(item);
    } catch (error) {
      console.error("Error creating inventory item:", error);
      res.status(500).json({ message: "Failed to create inventory item" });
    }
  });

  app.get('/api/households/:id/inventory', isAuthenticated, async (req: any, res) => {
    try {
      const householdId = parseInt(req.params.id);
      const { category } = req.query;
      
      let items;
      if (category === 'low-stock') {
        items = await storage.getLowStockItems(householdId);
      } else if (category === 'expiring') {
        items = await storage.getExpiringItems(householdId);
      } else {
        items = await storage.getInventoryItems(householdId);
      }
      
      res.json(items);
    } catch (error) {
      console.error("Error fetching inventory:", error);
      res.status(500).json({ message: "Failed to fetch inventory" });
    }
  });

  app.put('/api/inventory/:id', isAuthenticated, async (req: any, res) => {
    try {
      const itemId = parseInt(req.params.id);
      const updates = req.body;
      
      const item = await storage.updateInventoryItem(itemId, updates);
      res.json(item);
    } catch (error) {
      console.error("Error updating inventory item:", error);
      res.status(500).json({ message: "Failed to update inventory item" });
    }
  });

  app.delete('/api/inventory/:id', isAuthenticated, async (req: any, res) => {
    try {
      const itemId = parseInt(req.params.id);
      await storage.deleteInventoryItem(itemId);
      res.json({ success: true });
    } catch (error) {
      console.error("Error deleting inventory item:", error);
      res.status(500).json({ message: "Failed to delete inventory item" });
    }
  });

  // Meal plan routes
  app.post('/api/meal-plans/generate', isAuthenticated, async (req: any, res) => {
    try {
      const userId = req.user.claims.sub;
      const { householdId, weekStartDate } = req.body;
      
      // Get household profiles
      const profiles = await storage.getHouseholdProfiles(householdId);
      const members = await storage.getHouseholdMembers(householdId);
      
      // Get available ingredients from inventory
      const inventory = await storage.getInventoryItems(householdId);
      const availableIngredients = inventory.map(item => item.name);
      
      // Collect dietary restrictions
      const dietaryRestrictions = profiles.reduce((acc: string[], profile) => {
        if (profile.restrictions) {
          acc.push(...profile.restrictions);
        }
        return acc;
      }, []);
      
      // Generate meal plan using AI
      const mealPlanResponse = await generateMealPlan({
        profiles,
        householdSize: members.length,
        weekStartDate,
        dietaryRestrictions,
        availableIngredients,
      });
      
      // Save meal plan to database
      const mealPlan = await storage.createMealPlan({
        householdId,
        weekStartDate,
        generatedById: userId,
      });
      
      // Save individual meals
      const savedMeals = [];
      for (const meal of mealPlanResponse.meals) {
        const savedMeal = await storage.createMeal({
          mealPlanId: mealPlan.id,
          ...meal,
        });
        savedMeals.push(savedMeal);
      }
      
      res.json({
        ...mealPlan,
        meals: savedMeals,
        nutritionSummary: mealPlanResponse.nutritionSummary,
      });
    } catch (error) {
      console.error("Error generating meal plan:", error);
      res.status(500).json({ message: "Failed to generate meal plan" });
    }
  });

  app.get('/api/households/:id/meal-plans/current', isAuthenticated, async (req: any, res) => {
    try {
      const householdId = parseInt(req.params.id);
      const mealPlan = await storage.getLatestMealPlan(householdId);
      res.json(mealPlan);
    } catch (error) {
      console.error("Error fetching current meal plan:", error);
      res.status(500).json({ message: "Failed to fetch current meal plan" });
    }
  });

  app.get('/api/households/:id/meal-plans/:weekStartDate', isAuthenticated, async (req: any, res) => {
    try {
      const householdId = parseInt(req.params.id);
      const { weekStartDate } = req.params;
      const mealPlan = await storage.getMealPlanWithMeals(householdId, weekStartDate);
      res.json(mealPlan);
    } catch (error) {
      console.error("Error fetching meal plan:", error);
      res.status(500).json({ message: "Failed to fetch meal plan" });
    }
  });

  // Create individual meal
  app.post('/api/meal-plans/:id/meals', isAuthenticated, async (req: any, res) => {
    try {
      const mealPlanId = parseInt(req.params.id);
      
      if (isNaN(mealPlanId)) {
        return res.status(400).json({ message: "Invalid meal plan ID" });
      }
      
      // Validate the request body
      const mealData = {
        mealPlanId,
        name: req.body.name,
        description: req.body.description || "",
        mealType: req.body.mealType,
        dayOfWeek: parseInt(req.body.dayOfWeek),
        calories: req.body.calories ? parseInt(req.body.calories) : null,
        imageUrl: req.body.imageUrl || "",
        ingredients: req.body.ingredients || [],
        instructions: req.body.instructions || "",
      };
      
      // Validate with schema
      const validatedMealData = insertMealSchema.parse(mealData);
      
      const meal = await storage.createMeal(validatedMealData);
      res.json(meal);
    } catch (error: any) {
      console.error("Error creating meal:", error);
      if (error.name === 'ZodError') {
        return res.status(400).json({ message: "Invalid meal data", errors: error.errors });
      }
      res.status(500).json({ message: "Failed to create meal" });
    }
  });

  // Meal approval routes
  app.post('/api/meals/:id/approve', isAuthenticated, async (req: any, res) => {
    try {
      const userId = req.user.claims.sub;
      const mealId = parseInt(req.params.id);
      const { approved, comment } = req.body;
      
      const approval = await storage.createMealApproval({
        mealId,
        userId,
        approved,
        comment,
      });
      
      res.json(approval);
    } catch (error) {
      console.error("Error creating meal approval:", error);
      res.status(500).json({ message: "Failed to create meal approval" });
    }
  });

  app.get('/api/meals/:id/approvals', isAuthenticated, async (req: any, res) => {
    try {
      const mealId = parseInt(req.params.id);
      const approvals = await storage.getMealApprovals(mealId);
      res.json(approvals);
    } catch (error) {
      console.error("Error fetching meal approvals:", error);
      res.status(500).json({ message: "Failed to fetch meal approvals" });
    }
  });

  // Meal comment routes
  app.post('/api/meal-plans/:id/comments', isAuthenticated, async (req: any, res) => {
    try {
      const userId = req.user.claims.sub;
      const mealPlanId = parseInt(req.params.id);
      const commentData = insertMealCommentSchema.parse({
        ...req.body,
        mealPlanId,
        userId,
      });
      
      const comment = await storage.createMealComment(commentData);
      res.json(comment);
    } catch (error) {
      console.error("Error creating meal comment:", error);
      res.status(500).json({ message: "Failed to create meal comment" });
    }
  });

  app.get('/api/meal-plans/:id/comments', isAuthenticated, async (req: any, res) => {
    try {
      const mealPlanId = parseInt(req.params.id);
      const comments = await storage.getMealComments(mealPlanId);
      res.json(comments);
    } catch (error) {
      console.error("Error fetching meal comments:", error);
      res.status(500).json({ message: "Failed to fetch meal comments" });
    }
  });

  // Shopping list routes
  app.post('/api/shopping-list', isAuthenticated, async (req: any, res) => {
    try {
      const userId = req.user.claims.sub;
      const itemData = insertShoppingListItemSchema.parse({
        ...req.body,
        addedById: userId,
      });
      
      const item = await storage.createShoppingListItem(itemData);
      res.json(item);
    } catch (error) {
      console.error("Error creating shopping list item:", error);
      res.status(500).json({ message: "Failed to create shopping list item" });
    }
  });

  app.get('/api/households/:id/shopping-list', isAuthenticated, async (req: any, res) => {
    try {
      const householdId = parseInt(req.params.id);
      const items = await storage.getShoppingListItems(householdId);
      res.json(items);
    } catch (error) {
      console.error("Error fetching shopping list:", error);
      res.status(500).json({ message: "Failed to fetch shopping list" });
    }
  });

  app.put('/api/shopping-list/:id', isAuthenticated, async (req: any, res) => {
    try {
      const itemId = parseInt(req.params.id);
      const updates = req.body;
      
      const item = await storage.updateShoppingListItem(itemId, updates);
      res.json(item);
    } catch (error) {
      console.error("Error updating shopping list item:", error);
      res.status(500).json({ message: "Failed to update shopping list item" });
    }
  });

  app.delete('/api/shopping-list/:id', isAuthenticated, async (req: any, res) => {
    try {
      const itemId = parseInt(req.params.id);
      await storage.deleteShoppingListItem(itemId);
      res.json({ success: true });
    } catch (error) {
      console.error("Error deleting shopping list item:", error);
      res.status(500).json({ message: "Failed to delete shopping list item" });
    }
  });

  // AI insights route
  app.get('/api/households/:id/insights', isAuthenticated, async (req: any, res) => {
    try {
      const householdId = parseInt(req.params.id);
      
      // Get data for AI analysis
      const inventory = await storage.getInventoryItems(householdId);
      const profiles = await storage.getHouseholdProfiles(householdId);
      const household = await storage.getHousehold(householdId);
      
      const weekStart = new Date();
      weekStart.setDate(weekStart.getDate() - 7);
      const expenses = await storage.getHouseholdExpenses(
        householdId,
        weekStart.toISOString(),
        new Date().toISOString()
      );
      
      const currentMealPlan = await storage.getLatestMealPlan(householdId);
      const recentMeals = currentMealPlan?.meals || [];
      
      // Generate AI insights
      const insights = await generateAIInsights({
        inventoryItems: inventory,
        expenses,
        profiles,
        recentMeals,
        weeklyBudget: household?.weeklyBudget ? parseFloat(household.weeklyBudget) : undefined,
      });
      
      res.json(insights);
    } catch (error) {
      console.error("Error generating insights:", error);
      res.status(500).json({ message: "Failed to generate insights" });
    }
  });

  // Dashboard stats route
  app.get('/api/households/:id/stats', isAuthenticated, async (req: any, res) => {
    try {
      const householdId = parseInt(req.params.id);
      
      // Get current week expenses
      const weekStart = new Date();
      weekStart.setDate(weekStart.getDate() - 7);
      const weekExpenses = await storage.getHouseholdExpenses(
        householdId,
        weekStart.toISOString(),
        new Date().toISOString()
      );
      
      const weeklySpent = weekExpenses.reduce((total, expense) => {
        return total + parseFloat(expense.amount || "0");
      }, 0);
      
      // Get low stock items count
      const lowStockItems = await storage.getLowStockItems(householdId);
      
      // Get household info
      const household = await storage.getHousehold(householdId);
      const members = await storage.getHouseholdMembers(householdId);
      
      // Get current meal plan
      const currentMealPlan = await storage.getLatestMealPlan(householdId);
      const plannedMeals = currentMealPlan?.meals?.length || 0;
      
      res.json({
        weeklySpent,
        weeklyBudget: household?.weeklyBudget ? parseFloat(household.weeklyBudget) : 300,
        lowStockCount: lowStockItems.length,
        plannedMeals,
        familyMembers: members.length,
      });
    } catch (error) {
      console.error("Error fetching dashboard stats:", error);
      res.status(500).json({ message: "Failed to fetch dashboard stats" });
    }
  });

  // Receipt analysis route
  app.post('/api/receipts/analyze', isAuthenticated, async (req: any, res) => {
    try {
      const { receiptText } = req.body;
      
      if (!receiptText) {
        return res.status(400).json({ message: "Receipt text is required" });
      }
      
      const analysis = await analyzeReceipt(receiptText);
      res.json(analysis);
    } catch (error) {
      console.error("Error analyzing receipt:", error);
      res.status(500).json({ message: "Failed to analyze receipt" });
    }
  });

  // Expense routes
  app.post('/api/expenses', isAuthenticated, async (req: any, res) => {
    try {
      const userId = req.user.claims.sub;
      const expenseData = insertExpenseSchema.parse({
        ...req.body,
        addedById: userId,
      });
      
      const expense = await storage.createExpense(expenseData);
      res.json(expense);
    } catch (error) {
      console.error("Error creating expense:", error);
      res.status(500).json({ message: "Failed to create expense" });
    }
  });

  app.get('/api/households/:id/expenses', isAuthenticated, async (req: any, res) => {
    try {
      const householdId = parseInt(req.params.id);
      const { startDate, endDate } = req.query;
      
      const expenses = await storage.getHouseholdExpenses(
        householdId,
        startDate as string,
        endDate as string
      );
      
      res.json(expenses);
    } catch (error) {
      console.error("Error fetching expenses:", error);
      res.status(500).json({ message: "Failed to fetch expenses" });
    }
  });

  const httpServer = createServer(app);
  return httpServer;
}
