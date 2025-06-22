import { useQuery } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { 
  DollarSign, 
  AlertTriangle, 
  Utensils, 
  Users, 
  Lightbulb, 
  Leaf, 
  Recycle,
  Camera,
  Plus,
  Wand2,
  List,
  Sun,
  Moon
} from "lucide-react";

export default function Dashboard() {
  const { data: households } = useQuery({
    queryKey: ["/api/households"],
    retry: false,
  });

  // Use the first household or default to ID 1
  const householdId = (households as any)?.[0]?.id || 1;

  const { data: stats, isLoading: statsLoading } = useQuery({
    queryKey: [`/api/households/${householdId}/stats`],
    enabled: !!householdId,
  });

  const { data: insights, isLoading: insightsLoading } = useQuery({
    queryKey: [`/api/households/${householdId}/insights`],
    enabled: !!householdId,
  });

  const { data: mealPlan } = useQuery({
    queryKey: [`/api/households/${householdId}/meal-plans/current`],
    enabled: !!householdId,
  });

  if (statsLoading) {
    return (
      <div className="space-y-6">
        <div className="animate-pulse">
          <div className="h-8 bg-slate-200 rounded w-1/3 mb-2"></div>
          <div className="h-4 bg-slate-200 rounded w-1/2"></div>
        </div>
      </div>
    );
  }

  const getTodaysMeals = () => {
    if (!mealPlan?.meals) return [];
    const today = new Date().getDay(); // 0 = Sunday, 1 = Monday, etc.
    const mondayBasedToday = today === 0 ? 6 : today - 1; // Convert to Monday = 0 based
    
    return mealPlan.meals.filter(meal => meal.dayOfWeek === mondayBasedToday);
  };

  const todaysMeals = getTodaysMeals();
  const breakfastMeal = todaysMeals.find(m => m.mealType === "breakfast");
  const lunchMeal = todaysMeals.find(m => m.mealType === "lunch");
  const dinnerMeal = todaysMeals.find(m => m.mealType === "dinner");

  const budgetPercentage = stats ? (stats.weeklySpent / stats.weeklyBudget) * 100 : 0;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="mb-6">
        <h2 className="text-2xl font-bold text-slate-900 mb-2">
          Good morning! 👋
        </h2>
        <p className="text-slate-600">Here's what's happening with your household today</p>
      </div>

      {/* Quick Stats Cards */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-8">
        <Card>
          <CardContent className="p-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-slate-600">This Week's Budget</p>
                <p className="text-2xl font-bold text-slate-900">
                  ${stats?.weeklySpent?.toFixed(2) || "0.00"}
                </p>
                <p className="text-xs text-slate-500">
                  of ${stats?.weeklyBudget?.toFixed(2) || "300.00"} budgeted
                </p>
              </div>
              <div className="bg-primary/10 p-3 rounded-lg">
                <DollarSign className="h-5 w-5 text-primary" />
              </div>
            </div>
            <div className="mt-4">
              <Progress value={budgetPercentage} className="h-2" />
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="p-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-slate-600">Low Stock Items</p>
                <p className="text-2xl font-bold text-slate-900">
                  {stats?.lowStockCount || 0}
                </p>
                <p className="text-xs text-secondary">Need restocking</p>
              </div>
              <div className="bg-secondary/10 p-3 rounded-lg">
                <AlertTriangle className="h-5 w-5 text-secondary" />
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="p-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-slate-600">Planned Meals</p>
                <p className="text-2xl font-bold text-slate-900">
                  {stats?.plannedMeals || 0}
                </p>
                <p className="text-xs text-primary">This week</p>
              </div>
              <div className="bg-accent/10 p-3 rounded-lg">
                <Utensils className="h-5 w-5 text-accent" />
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="p-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-slate-600">Family Members</p>
                <p className="text-2xl font-bold text-slate-900">
                  {stats?.familyMembers || 0}
                </p>
                <p className="text-xs text-slate-500">Active profiles</p>
              </div>
              <div className="bg-primary/10 p-3 rounded-lg">
                <Users className="h-5 w-5 text-primary" />
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* AI Insights & Today's Meals */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-8">
        {/* AI Insights */}
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Lightbulb className="h-5 w-5 text-primary" />
              AI Insights
              <Badge variant="secondary" className="ml-auto">
                Updated 2h ago
              </Badge>
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {insightsLoading ? (
              <div className="space-y-3">
                {[1, 2, 3].map((i) => (
                  <div key={i} className="animate-pulse">
                    <div className="h-4 bg-slate-200 rounded w-3/4"></div>
                    <div className="h-3 bg-slate-200 rounded w-1/2 mt-2"></div>
                  </div>
                ))}
              </div>
            ) : insights && insights.length > 0 ? (
              insights.slice(0, 3).map((insight: any, index: number) => (
                <div key={index} className="p-4 bg-gradient-to-r from-primary/5 to-accent/5 rounded-lg border border-primary/20">
                  <div className="flex items-start space-x-3">
                    <Lightbulb className="h-5 w-5 text-secondary mt-1" />
                    <div>
                      <h4 className="font-medium text-slate-900">{insight.title}</h4>
                      <p className="text-sm text-slate-600 mt-1">{insight.message}</p>
                    </div>
                  </div>
                </div>
              ))
            ) : (
              <div className="text-center py-8 text-slate-500">
                <Lightbulb className="h-12 w-12 mx-auto mb-4 text-slate-300" />
                <p>No insights available yet. Add some inventory items and meal plans to get started!</p>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Today's Meals */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Utensils className="h-5 w-5 text-accent" />
              Today's Meals
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {/* Breakfast */}
            <div className="flex items-center space-x-3 p-3 bg-slate-50 rounded-lg">
              <div className="w-12 h-12 bg-gradient-to-br from-secondary to-primary rounded-lg flex items-center justify-center">
                <Sun className="h-6 w-6 text-white" />
              </div>
              <div className="flex-1">
                <h4 className="font-medium text-slate-900">
                  {breakfastMeal?.name || "No breakfast planned"}
                </h4>
                {breakfastMeal?.description && (
                  <p className="text-sm text-slate-600">{breakfastMeal.description}</p>
                )}
                {breakfastMeal?.calories && (
                  <Badge variant="outline" className="mt-1">
                    {breakfastMeal.calories} cal
                  </Badge>
                )}
              </div>
            </div>

            {/* Lunch */}
            <div className="flex items-center space-x-3 p-3 bg-slate-50 rounded-lg">
              <div className="w-12 h-12 bg-gradient-to-br from-accent to-secondary rounded-lg flex items-center justify-center">
                <Sun className="h-6 w-6 text-white transform rotate-90" />
              </div>
              <div className="flex-1">
                <h4 className="font-medium text-slate-900">
                  {lunchMeal?.name || "No lunch planned"}
                </h4>
                {lunchMeal?.description && (
                  <p className="text-sm text-slate-600">{lunchMeal.description}</p>
                )}
                {lunchMeal?.calories && (
                  <Badge variant="outline" className="mt-1">
                    {lunchMeal.calories} cal
                  </Badge>
                )}
              </div>
            </div>

            {/* Dinner */}
            <div className="flex items-center space-x-3 p-3 bg-slate-50 rounded-lg">
              <div className="w-12 h-12 bg-gradient-to-br from-primary to-accent rounded-lg flex items-center justify-center">
                <Moon className="h-6 w-6 text-white" />
              </div>
              <div className="flex-1">
                <h4 className="font-medium text-slate-900">
                  {dinnerMeal?.name || "No dinner planned"}
                </h4>
                {dinnerMeal?.description && (
                  <p className="text-sm text-slate-600">{dinnerMeal.description}</p>
                )}
                {dinnerMeal?.calories && (
                  <Badge variant="outline" className="mt-1">
                    {dinnerMeal.calories} cal
                  </Badge>
                )}
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Quick Actions */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Wand2 className="h-5 w-5 text-secondary" />
            Quick Actions
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <Button 
              variant="outline" 
              className="p-4 h-auto flex flex-col items-center space-y-2 hover:bg-primary/5 hover:border-primary/20"
            >
              <Camera className="h-6 w-6 text-primary" />
              <span className="text-sm font-medium">Upload Receipt</span>
            </Button>
            
            <Button 
              variant="outline" 
              className="p-4 h-auto flex flex-col items-center space-y-2 hover:bg-secondary/5 hover:border-secondary/20"
            >
              <Plus className="h-6 w-6 text-secondary" />
              <span className="text-sm font-medium">Add Item</span>
            </Button>
            
            <Button 
              variant="outline" 
              className="p-4 h-auto flex flex-col items-center space-y-2 hover:bg-accent/5 hover:border-accent/20"
            >
              <Wand2 className="h-6 w-6 text-accent" />
              <span className="text-sm font-medium">Generate Plan</span>
            </Button>
            
            <Button 
              variant="outline" 
              className="p-4 h-auto flex flex-col items-center space-y-2 hover:bg-slate-100"
            >
              <List className="h-6 w-6 text-slate-600" />
              <span className="text-sm font-medium">Shopping List</span>
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
