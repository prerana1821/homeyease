import {
  users,
  households,
  householdMembers,
  profiles,
  inventoryItems,
  mealPlans,
  meals,
  mealApprovals,
  mealComments,
  shoppingListItems,
  expenses,
  type User,
  type UpsertUser,
  type Household,
  type InsertHousehold,
  type HouseholdMember,
  type InsertHouseholdMember,
  type Profile,
  type InsertProfile,
  type InventoryItem,
  type InsertInventoryItem,
  type MealPlan,
  type InsertMealPlan,
  type Meal,
  type InsertMeal,
  type MealApproval,
  type InsertMealApproval,
  type MealComment,
  type InsertMealComment,
  type ShoppingListItem,
  type InsertShoppingListItem,
  type Expense,
  type InsertExpense,
} from "@shared/schema";
import { db } from "./db";
import { eq, and, gte, lte, desc, asc } from "drizzle-orm";

// Interface for storage operations
export interface IStorage {
  // User operations (IMPORTANT) these user operations are mandatory for Replit Auth.
  getUser(id: string): Promise<User | undefined>;
  upsertUser(user: UpsertUser): Promise<User>;
  
  // Household operations
  createHousehold(household: InsertHousehold): Promise<Household>;
  getHousehold(id: number): Promise<Household | undefined>;
  getUserHouseholds(userId: string): Promise<Household[]>;
  addHouseholdMember(member: InsertHouseholdMember): Promise<HouseholdMember>;
  getHouseholdMembers(householdId: number): Promise<(HouseholdMember & { user: User })[]>;
  
  // Profile operations
  createProfile(profile: InsertProfile): Promise<Profile>;
  getProfile(userId: string, householdId: number): Promise<Profile | undefined>;
  getHouseholdProfiles(householdId: number): Promise<(Profile & { user: User })[]>;
  updateProfile(userId: string, householdId: number, updates: Partial<InsertProfile>): Promise<Profile>;
  
  // Inventory operations
  createInventoryItem(item: InsertInventoryItem): Promise<InventoryItem>;
  getInventoryItems(householdId: number): Promise<InventoryItem[]>;
  getLowStockItems(householdId: number): Promise<InventoryItem[]>;
  getExpiringItems(householdId: number): Promise<InventoryItem[]>;
  updateInventoryItem(id: number, updates: Partial<InsertInventoryItem>): Promise<InventoryItem>;
  deleteInventoryItem(id: number): Promise<void>;
  
  // Meal plan operations
  createMealPlan(mealPlan: InsertMealPlan): Promise<MealPlan>;
  getMealPlan(householdId: number, weekStartDate: string): Promise<MealPlan | undefined>;
  getMealPlanWithMeals(householdId: number, weekStartDate: string): Promise<(MealPlan & { meals: Meal[] }) | undefined>;
  getLatestMealPlan(householdId: number): Promise<(MealPlan & { meals: Meal[] }) | undefined>;
  
  // Meal operations
  createMeal(meal: InsertMeal): Promise<Meal>;
  getMealsForPlan(mealPlanId: number): Promise<Meal[]>;
  
  // Meal approval operations
  createMealApproval(approval: InsertMealApproval): Promise<MealApproval>;
  getMealApprovals(mealId: number): Promise<(MealApproval & { user: User })[]>;
  getUserMealApproval(mealId: number, userId: string): Promise<MealApproval | undefined>;
  
  // Meal comment operations
  createMealComment(comment: InsertMealComment): Promise<MealComment>;
  getMealComments(mealPlanId: number): Promise<(MealComment & { user: User })[]>;
  
  // Shopping list operations
  createShoppingListItem(item: InsertShoppingListItem): Promise<ShoppingListItem>;
  getShoppingListItems(householdId: number): Promise<ShoppingListItem[]>;
  updateShoppingListItem(id: number, updates: Partial<InsertShoppingListItem>): Promise<ShoppingListItem>;
  deleteShoppingListItem(id: number): Promise<void>;
  
  // Expense operations
  createExpense(expense: InsertExpense): Promise<Expense>;
  getHouseholdExpenses(householdId: number, startDate?: string, endDate?: string): Promise<Expense[]>;
}

export class DatabaseStorage implements IStorage {
  // User operations (IMPORTANT) these user operations are mandatory for Replit Auth.
  async getUser(id: string): Promise<User | undefined> {
    const [user] = await db.select().from(users).where(eq(users.id, id));
    return user || undefined;
  }

  async upsertUser(userData: UpsertUser): Promise<User> {
    const [user] = await db
      .insert(users)
      .values(userData)
      .onConflictDoUpdate({
        target: users.id,
        set: {
          ...userData,
          updatedAt: new Date(),
        },
      })
      .returning();
    return user;
  }

  // Household operations
  async createHousehold(household: InsertHousehold): Promise<Household> {
    const [newHousehold] = await db
      .insert(households)
      .values(household)
      .returning();
    return newHousehold;
  }

  async getHousehold(id: number): Promise<Household | undefined> {
    const [household] = await db
      .select()
      .from(households)
      .where(eq(households.id, id));
    return household || undefined;
  }

  async getUserHouseholds(userId: string): Promise<Household[]> {
    const userHouseholds = await db
      .select({
        id: households.id,
        name: households.name,
        createdById: households.createdById,
        weeklyBudget: households.weeklyBudget,
        createdAt: households.createdAt,
        updatedAt: households.updatedAt,
      })
      .from(households)
      .innerJoin(householdMembers, eq(households.id, householdMembers.householdId))
      .where(eq(householdMembers.userId, userId));
    return userHouseholds;
  }

  async addHouseholdMember(member: InsertHouseholdMember): Promise<HouseholdMember> {
    const [newMember] = await db
      .insert(householdMembers)
      .values(member)
      .returning();
    return newMember;
  }

  async getHouseholdMembers(householdId: number): Promise<(HouseholdMember & { user: User })[]> {
    const members = await db
      .select({
        householdId: householdMembers.householdId,
        userId: householdMembers.userId,
        role: householdMembers.role,
        joinedAt: householdMembers.joinedAt,
        user: {
          id: users.id,
          email: users.email,
          firstName: users.firstName,
          lastName: users.lastName,
          profileImageUrl: users.profileImageUrl,
          createdAt: users.createdAt,
          updatedAt: users.updatedAt,
        },
      })
      .from(householdMembers)
      .innerJoin(users, eq(householdMembers.userId, users.id))
      .where(eq(householdMembers.householdId, householdId));
    return members;
  }

  // Profile operations
  async createProfile(profile: InsertProfile): Promise<Profile> {
    const [newProfile] = await db
      .insert(profiles)
      .values(profile)
      .returning();
    return newProfile;
  }

  async getProfile(userId: string, householdId: number): Promise<Profile | undefined> {
    const [profile] = await db
      .select()
      .from(profiles)
      .where(and(eq(profiles.userId, userId), eq(profiles.householdId, householdId)));
    return profile || undefined;
  }

  async getHouseholdProfiles(householdId: number): Promise<(Profile & { user: User })[]> {
    const householdProfiles = await db
      .select({
        id: profiles.id,
        userId: profiles.userId,
        householdId: profiles.householdId,
        dailyCalories: profiles.dailyCalories,
        age: profiles.age,
        dietType: profiles.dietType,
        goal: profiles.goal,
        restrictions: profiles.restrictions,
        preferences: profiles.preferences,
        createdAt: profiles.createdAt,
        updatedAt: profiles.updatedAt,
        user: {
          id: users.id,
          email: users.email,
          firstName: users.firstName,
          lastName: users.lastName,
          profileImageUrl: users.profileImageUrl,
          createdAt: users.createdAt,
          updatedAt: users.updatedAt,
        },
      })
      .from(profiles)
      .innerJoin(users, eq(profiles.userId, users.id))
      .where(eq(profiles.householdId, householdId));
    return householdProfiles;
  }

  async updateProfile(userId: string, householdId: number, updates: Partial<InsertProfile>): Promise<Profile> {
    const [updatedProfile] = await db
      .update(profiles)
      .set({ ...updates, updatedAt: new Date() })
      .where(and(eq(profiles.userId, userId), eq(profiles.householdId, householdId)))
      .returning();
    return updatedProfile;
  }

  // Inventory operations
  async createInventoryItem(item: InsertInventoryItem): Promise<InventoryItem> {
    const [newItem] = await db
      .insert(inventoryItems)
      .values(item)
      .returning();
    return newItem;
  }

  async getInventoryItems(householdId: number): Promise<InventoryItem[]> {
    const items = await db
      .select()
      .from(inventoryItems)
      .where(eq(inventoryItems.householdId, householdId))
      .orderBy(asc(inventoryItems.name));
    return items;
  }

  async getLowStockItems(householdId: number): Promise<InventoryItem[]> {
    const items = await db
      .select()
      .from(inventoryItems)
      .where(eq(inventoryItems.householdId, householdId))
      .orderBy(asc(inventoryItems.name));
    
    // Filter low stock items (this is a simplified version)
    return items.filter(item => {
      if (!item.lowStockThreshold) return false;
      const quantity = parseInt(item.quantity || "0");
      return quantity <= item.lowStockThreshold;
    });
  }

  async getExpiringItems(householdId: number): Promise<InventoryItem[]> {
    const threeDaysFromNow = new Date();
    threeDaysFromNow.setDate(threeDaysFromNow.getDate() + 3);
    
    const items = await db
      .select()
      .from(inventoryItems)
      .where(
        and(
          eq(inventoryItems.householdId, householdId),
          lte(inventoryItems.expiryDate, threeDaysFromNow.toISOString().split('T')[0])
        )
      )
      .orderBy(asc(inventoryItems.expiryDate));
    return items;
  }

  async updateInventoryItem(id: number, updates: Partial<InsertInventoryItem>): Promise<InventoryItem> {
    const [updatedItem] = await db
      .update(inventoryItems)
      .set({ ...updates, updatedAt: new Date() })
      .where(eq(inventoryItems.id, id))
      .returning();
    return updatedItem;
  }

  async deleteInventoryItem(id: number): Promise<void> {
    await db.delete(inventoryItems).where(eq(inventoryItems.id, id));
  }

  // Meal plan operations
  async createMealPlan(mealPlan: InsertMealPlan): Promise<MealPlan> {
    const [newMealPlan] = await db
      .insert(mealPlans)
      .values(mealPlan)
      .returning();
    return newMealPlan;
  }

  async getMealPlan(householdId: number, weekStartDate: string): Promise<MealPlan | undefined> {
    const [mealPlan] = await db
      .select()
      .from(mealPlans)
      .where(
        and(
          eq(mealPlans.householdId, householdId),
          eq(mealPlans.weekStartDate, weekStartDate)
        )
      );
    return mealPlan || undefined;
  }

  async getMealPlanWithMeals(householdId: number, weekStartDate: string): Promise<(MealPlan & { meals: Meal[] }) | undefined> {
    const mealPlan = await this.getMealPlan(householdId, weekStartDate);
    if (!mealPlan) return undefined;

    const planMeals = await this.getMealsForPlan(mealPlan.id);
    return { ...mealPlan, meals: planMeals };
  }

  async getLatestMealPlan(householdId: number): Promise<(MealPlan & { meals: Meal[] }) | undefined> {
    const [mealPlan] = await db
      .select()
      .from(mealPlans)
      .where(eq(mealPlans.householdId, householdId))
      .orderBy(desc(mealPlans.weekStartDate))
      .limit(1);

    if (!mealPlan) return undefined;

    const planMeals = await this.getMealsForPlan(mealPlan.id);
    return { ...mealPlan, meals: planMeals };
  }

  // Meal operations
  async createMeal(meal: InsertMeal): Promise<Meal> {
    const [newMeal] = await db
      .insert(meals)
      .values(meal)
      .returning();
    return newMeal;
  }

  async getMealsForPlan(mealPlanId: number): Promise<Meal[]> {
    const planMeals = await db
      .select()
      .from(meals)
      .where(eq(meals.mealPlanId, mealPlanId))
      .orderBy(asc(meals.dayOfWeek), asc(meals.mealType));
    return planMeals;
  }

  // Meal approval operations
  async createMealApproval(approval: InsertMealApproval): Promise<MealApproval> {
    const [newApproval] = await db
      .insert(mealApprovals)
      .values(approval)
      .onConflictDoUpdate({
        target: [mealApprovals.mealId, mealApprovals.userId],
        set: {
          approved: approval.approved,
          comment: approval.comment,
        },
      })
      .returning();
    return newApproval;
  }

  async getMealApprovals(mealId: number): Promise<(MealApproval & { user: User })[]> {
    const approvals = await db
      .select({
        id: mealApprovals.id,
        mealId: mealApprovals.mealId,
        userId: mealApprovals.userId,
        approved: mealApprovals.approved,
        comment: mealApprovals.comment,
        createdAt: mealApprovals.createdAt,
        user: {
          id: users.id,
          email: users.email,
          firstName: users.firstName,
          lastName: users.lastName,
          profileImageUrl: users.profileImageUrl,
          createdAt: users.createdAt,
          updatedAt: users.updatedAt,
        },
      })
      .from(mealApprovals)
      .innerJoin(users, eq(mealApprovals.userId, users.id))
      .where(eq(mealApprovals.mealId, mealId));
    return approvals;
  }

  async getUserMealApproval(mealId: number, userId: string): Promise<MealApproval | undefined> {
    const [approval] = await db
      .select()
      .from(mealApprovals)
      .where(and(eq(mealApprovals.mealId, mealId), eq(mealApprovals.userId, userId)));
    return approval || undefined;
  }

  // Meal comment operations
  async createMealComment(comment: InsertMealComment): Promise<MealComment> {
    const [newComment] = await db
      .insert(mealComments)
      .values(comment)
      .returning();
    return newComment;
  }

  async getMealComments(mealPlanId: number): Promise<(MealComment & { user: User })[]> {
    const comments = await db
      .select({
        id: mealComments.id,
        mealPlanId: mealComments.mealPlanId,
        userId: mealComments.userId,
        comment: mealComments.comment,
        mealType: mealComments.mealType,
        dayOfWeek: mealComments.dayOfWeek,
        createdAt: mealComments.createdAt,
        user: {
          id: users.id,
          email: users.email,
          firstName: users.firstName,
          lastName: users.lastName,
          profileImageUrl: users.profileImageUrl,
          createdAt: users.createdAt,
          updatedAt: users.updatedAt,
        },
      })
      .from(mealComments)
      .innerJoin(users, eq(mealComments.userId, users.id))
      .where(eq(mealComments.mealPlanId, mealPlanId))
      .orderBy(desc(mealComments.createdAt));
    return comments;
  }

  // Shopping list operations
  async createShoppingListItem(item: InsertShoppingListItem): Promise<ShoppingListItem> {
    const [newItem] = await db
      .insert(shoppingListItems)
      .values(item)
      .returning();
    return newItem;
  }

  async getShoppingListItems(householdId: number): Promise<ShoppingListItem[]> {
    const items = await db
      .select()
      .from(shoppingListItems)
      .where(eq(shoppingListItems.householdId, householdId))
      .orderBy(asc(shoppingListItems.completed), desc(shoppingListItems.createdAt));
    return items;
  }

  async updateShoppingListItem(id: number, updates: Partial<InsertShoppingListItem>): Promise<ShoppingListItem> {
    const [updatedItem] = await db
      .update(shoppingListItems)
      .set(updates)
      .where(eq(shoppingListItems.id, id))
      .returning();
    return updatedItem;
  }

  async deleteShoppingListItem(id: number): Promise<void> {
    await db.delete(shoppingListItems).where(eq(shoppingListItems.id, id));
  }

  // Expense operations
  async createExpense(expense: InsertExpense): Promise<Expense> {
    const [newExpense] = await db
      .insert(expenses)
      .values(expense)
      .returning();
    return newExpense;
  }

  async getHouseholdExpenses(householdId: number, startDate?: string, endDate?: string): Promise<Expense[]> {
    if (startDate && endDate) {
      const householdExpenses = await db
        .select()
        .from(expenses)
        .where(
          and(
            eq(expenses.householdId, householdId),
            gte(expenses.createdAt, new Date(startDate)),
            lte(expenses.createdAt, new Date(endDate))
          )
        )
        .orderBy(desc(expenses.createdAt));
      return householdExpenses;
    }

    const householdExpenses = await db
      .select()
      .from(expenses)
      .where(eq(expenses.householdId, householdId))
      .orderBy(desc(expenses.createdAt));
    
    return householdExpenses;
  }
}

export const storage = new DatabaseStorage();
