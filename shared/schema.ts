import {
  pgTable,
  text,
  varchar,
  timestamp,
  jsonb,
  index,
  serial,
  integer,
  decimal,
  boolean,
  date,
  primaryKey,
} from "drizzle-orm/pg-core";
import { relations } from "drizzle-orm";
import { createInsertSchema } from "drizzle-zod";
import { z } from "zod";

// Session storage table.
// (IMPORTANT) This table is mandatory for Replit Auth, don't drop it.
export const sessions = pgTable(
  "sessions",
  {
    sid: varchar("sid").primaryKey(),
    sess: jsonb("sess").notNull(),
    expire: timestamp("expire").notNull(),
  },
  (table) => [index("IDX_session_expire").on(table.expire)],
);

// User storage table.
// (IMPORTANT) This table is mandatory for Replit Auth, don't drop it.
export const users = pgTable("users", {
  id: varchar("id").primaryKey().notNull(),
  email: varchar("email").unique(),
  firstName: varchar("first_name"),
  lastName: varchar("last_name"),
  profileImageUrl: varchar("profile_image_url"),
  createdAt: timestamp("created_at").defaultNow(),
  updatedAt: timestamp("updated_at").defaultNow(),
});

export const households = pgTable("households", {
  id: serial("id").primaryKey(),
  name: varchar("name", { length: 255 }).notNull(),
  createdById: varchar("created_by_id").notNull().references(() => users.id),
  weeklyBudget: decimal("weekly_budget", { precision: 10, scale: 2 }),
  createdAt: timestamp("created_at").defaultNow(),
  updatedAt: timestamp("updated_at").defaultNow(),
});

export const householdMembers = pgTable("household_members", {
  householdId: integer("household_id").notNull().references(() => households.id),
  userId: varchar("user_id").notNull().references(() => users.id),
  role: varchar("role", { length: 50 }).notNull().default("member"),
  joinedAt: timestamp("joined_at").defaultNow(),
}, (table) => ({
  pk: primaryKey({ columns: [table.householdId, table.userId] }),
}));

export const profiles = pgTable("profiles", {
  id: serial("id").primaryKey(),
  userId: varchar("user_id").notNull().references(() => users.id),
  householdId: integer("household_id").notNull().references(() => households.id),
  dailyCalories: integer("daily_calories"),
  age: integer("age"),
  dietType: varchar("diet_type", { length: 100 }),
  goal: varchar("goal", { length: 100 }),
  restrictions: text("restrictions").array(),
  preferences: text("preferences").array(),
  createdAt: timestamp("created_at").defaultNow(),
  updatedAt: timestamp("updated_at").defaultNow(),
});

export const inventoryItems = pgTable("inventory_items", {
  id: serial("id").primaryKey(),
  householdId: integer("household_id").notNull().references(() => households.id),
  name: varchar("name", { length: 255 }).notNull(),
  category: varchar("category", { length: 100 }),
  quantity: varchar("quantity", { length: 100 }),
  unit: varchar("unit", { length: 50 }),
  cost: decimal("cost", { precision: 10, scale: 2 }),
  expiryDate: date("expiry_date"),
  lowStockThreshold: integer("low_stock_threshold"),
  addedById: varchar("added_by_id").notNull().references(() => users.id),
  createdAt: timestamp("created_at").defaultNow(),
  updatedAt: timestamp("updated_at").defaultNow(),
});

export const mealPlans = pgTable("meal_plans", {
  id: serial("id").primaryKey(),
  householdId: integer("household_id").notNull().references(() => households.id),
  weekStartDate: date("week_start_date").notNull(),
  generatedAt: timestamp("generated_at").defaultNow(),
  generatedById: varchar("generated_by_id").notNull().references(() => users.id),
});

export const meals = pgTable("meals", {
  id: serial("id").primaryKey(),
  mealPlanId: integer("meal_plan_id").notNull().references(() => mealPlans.id),
  name: varchar("name", { length: 255 }).notNull(),
  description: text("description"),
  mealType: varchar("meal_type", { length: 50 }).notNull(), // breakfast, lunch, dinner
  dayOfWeek: integer("day_of_week").notNull(), // 0-6
  calories: integer("calories"),
  imageUrl: varchar("image_url"),
  ingredients: jsonb("ingredients"),
  instructions: text("instructions"),
});

export const mealApprovals = pgTable("meal_approvals", {
  id: serial("id").primaryKey(),
  mealId: integer("meal_id").notNull().references(() => meals.id),
  userId: varchar("user_id").notNull().references(() => users.id),
  approved: boolean("approved").notNull(),
  comment: text("comment"),
  createdAt: timestamp("created_at").defaultNow(),
});

export const mealComments = pgTable("meal_comments", {
  id: serial("id").primaryKey(),
  mealPlanId: integer("meal_plan_id").notNull().references(() => mealPlans.id),
  userId: varchar("user_id").notNull().references(() => users.id),
  comment: text("comment").notNull(),
  mealType: varchar("meal_type", { length: 50 }),
  dayOfWeek: integer("day_of_week"),
  createdAt: timestamp("created_at").defaultNow(),
});

export const shoppingListItems = pgTable("shopping_list_items", {
  id: serial("id").primaryKey(),
  householdId: integer("household_id").notNull().references(() => households.id),
  name: varchar("name", { length: 255 }).notNull(),
  reason: varchar("reason", { length: 255 }),
  estimatedCost: decimal("estimated_cost", { precision: 10, scale: 2 }),
  store: varchar("store", { length: 100 }),
  completed: boolean("completed").default(false),
  addedById: varchar("added_by_id").notNull().references(() => users.id),
  createdAt: timestamp("created_at").defaultNow(),
});

export const expenses = pgTable("expenses", {
  id: serial("id").primaryKey(),
  householdId: integer("household_id").notNull().references(() => households.id),
  amount: decimal("amount", { precision: 10, scale: 2 }).notNull(),
  description: text("description"),
  category: varchar("category", { length: 100 }),
  receiptData: jsonb("receipt_data"),
  addedById: varchar("added_by_id").notNull().references(() => users.id),
  createdAt: timestamp("created_at").defaultNow(),
});

// Relations
export const usersRelations = relations(users, ({ many }) => ({
  households: many(householdMembers),
  profiles: many(profiles),
  inventoryItems: many(inventoryItems),
  mealApprovals: many(mealApprovals),
  mealComments: many(mealComments),
  shoppingListItems: many(shoppingListItems),
  expenses: many(expenses),
}));

export const householdsRelations = relations(households, ({ one, many }) => ({
  createdBy: one(users, {
    fields: [households.createdById],
    references: [users.id],
  }),
  members: many(householdMembers),
  profiles: many(profiles),
  inventoryItems: many(inventoryItems),
  mealPlans: many(mealPlans),
  shoppingListItems: many(shoppingListItems),
  expenses: many(expenses),
}));

export const householdMembersRelations = relations(householdMembers, ({ one }) => ({
  household: one(households, {
    fields: [householdMembers.householdId],
    references: [households.id],
  }),
  user: one(users, {
    fields: [householdMembers.userId],
    references: [users.id],
  }),
}));

export const profilesRelations = relations(profiles, ({ one }) => ({
  user: one(users, {
    fields: [profiles.userId],
    references: [users.id],
  }),
  household: one(households, {
    fields: [profiles.householdId],
    references: [households.id],
  }),
}));

export const inventoryItemsRelations = relations(inventoryItems, ({ one }) => ({
  household: one(households, {
    fields: [inventoryItems.householdId],
    references: [households.id],
  }),
  addedBy: one(users, {
    fields: [inventoryItems.addedById],
    references: [users.id],
  }),
}));

export const mealPlansRelations = relations(mealPlans, ({ one, many }) => ({
  household: one(households, {
    fields: [mealPlans.householdId],
    references: [households.id],
  }),
  generatedBy: one(users, {
    fields: [mealPlans.generatedById],
    references: [users.id],
  }),
  meals: many(meals),
  comments: many(mealComments),
}));

export const mealsRelations = relations(meals, ({ one, many }) => ({
  mealPlan: one(mealPlans, {
    fields: [meals.mealPlanId],
    references: [mealPlans.id],
  }),
  approvals: many(mealApprovals),
}));

export const mealApprovalsRelations = relations(mealApprovals, ({ one }) => ({
  meal: one(meals, {
    fields: [mealApprovals.mealId],
    references: [meals.id],
  }),
  user: one(users, {
    fields: [mealApprovals.userId],
    references: [users.id],
  }),
}));

export const mealCommentsRelations = relations(mealComments, ({ one }) => ({
  mealPlan: one(mealPlans, {
    fields: [mealComments.mealPlanId],
    references: [mealPlans.id],
  }),
  user: one(users, {
    fields: [mealComments.userId],
    references: [users.id],
  }),
}));

export const shoppingListItemsRelations = relations(shoppingListItems, ({ one }) => ({
  household: one(households, {
    fields: [shoppingListItems.householdId],
    references: [households.id],
  }),
  addedBy: one(users, {
    fields: [shoppingListItems.addedById],
    references: [users.id],
  }),
}));

export const expensesRelations = relations(expenses, ({ one }) => ({
  household: one(households, {
    fields: [expenses.householdId],
    references: [households.id],
  }),
  addedBy: one(users, {
    fields: [expenses.addedById],
    references: [users.id],
  }),
}));

// Types
export type UpsertUser = typeof users.$inferInsert;
export type User = typeof users.$inferSelect;

export type Household = typeof households.$inferSelect;
export type InsertHousehold = typeof households.$inferInsert;

export type HouseholdMember = typeof householdMembers.$inferSelect;
export type InsertHouseholdMember = typeof householdMembers.$inferInsert;

export type Profile = typeof profiles.$inferSelect;
export type InsertProfile = typeof profiles.$inferInsert;

export type InventoryItem = typeof inventoryItems.$inferSelect;
export type InsertInventoryItem = typeof inventoryItems.$inferInsert;

export type MealPlan = typeof mealPlans.$inferSelect;
export type InsertMealPlan = typeof mealPlans.$inferInsert;

export type Meal = typeof meals.$inferSelect;
export type InsertMeal = typeof meals.$inferInsert;

export type MealApproval = typeof mealApprovals.$inferSelect;
export type InsertMealApproval = typeof mealApprovals.$inferInsert;

export type MealComment = typeof mealComments.$inferSelect;
export type InsertMealComment = typeof mealComments.$inferInsert;

export type ShoppingListItem = typeof shoppingListItems.$inferSelect;
export type InsertShoppingListItem = typeof shoppingListItems.$inferInsert;

export type Expense = typeof expenses.$inferSelect;
export type InsertExpense = typeof expenses.$inferInsert;

// Zod schemas
export const insertHouseholdSchema = createInsertSchema(households).omit({
  id: true,
  createdAt: true,
  updatedAt: true,
});

export const insertProfileSchema = createInsertSchema(profiles).omit({
  id: true,
  createdAt: true,
  updatedAt: true,
});

export const insertInventoryItemSchema = createInsertSchema(inventoryItems).omit({
  id: true,
  createdAt: true,
  updatedAt: true,
});

export const insertMealPlanSchema = createInsertSchema(mealPlans).omit({
  id: true,
  generatedAt: true,
});

export const insertMealSchema = createInsertSchema(meals).omit({
  id: true,
});

export const insertMealApprovalSchema = createInsertSchema(mealApprovals).omit({
  id: true,
  createdAt: true,
});

export const insertMealCommentSchema = createInsertSchema(mealComments).omit({
  id: true,
  createdAt: true,
});

export const insertShoppingListItemSchema = createInsertSchema(shoppingListItems).omit({
  id: true,
  createdAt: true,
});

export const insertExpenseSchema = createInsertSchema(expenses).omit({
  id: true,
  createdAt: true,
});
