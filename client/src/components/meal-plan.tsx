import { useState } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Textarea } from "@/components/ui/textarea";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { useToast } from "@/hooks/use-toast";
import { apiRequest, queryClient } from "@/lib/queryClient";
import { 
  Calendar,
  Wand2,
  ThumbsUp,
  ThumbsDown,
  MessageCircle,
  Sun,
  Moon,
  Send
} from "lucide-react";

export default function MealPlan() {
  const { toast } = useToast();
  const [newComment, setNewComment] = useState("");
  
  const { data: households } = useQuery({
    queryKey: ["/api/households"],
    retry: false,
  });

  const householdId = households?.[0]?.id || 1;

  // Get current week's start date (Monday)
  const getCurrentWeekStart = () => {
    const now = new Date();
    const day = now.getDay();
    const diff = now.getDate() - day + (day === 0 ? -6 : 1); // Adjust when day is Sunday
    const monday = new Date(now.setDate(diff));
    return monday.toISOString().split('T')[0];
  };

  const weekStartDate = getCurrentWeekStart();

  const { data: mealPlan, isLoading } = useQuery({
    queryKey: [`/api/households/${householdId}/meal-plans/${weekStartDate}`],
    enabled: !!householdId,
  });

  const { data: comments } = useQuery({
    queryKey: [`/api/meal-plans/${mealPlan?.id}/comments`],
    enabled: !!mealPlan?.id,
  });

  const generatePlanMutation = useMutation({
    mutationFn: async () => {
      return apiRequest("POST", "/api/meal-plans/generate", {
        householdId,
        weekStartDate,
      });
    },
    onSuccess: () => {
      toast({
        title: "Success",
        description: "New meal plan generated successfully!",
      });
      queryClient.invalidateQueries({ queryKey: [`/api/households/${householdId}/meal-plans/${weekStartDate}`] });
    },
    onError: (error) => {
      toast({
        title: "Error",
        description: "Failed to generate meal plan. Please try again.",
        variant: "destructive",
      });
    },
  });

  const approveMealMutation = useMutation({
    mutationFn: async ({ mealId, approved }: { mealId: number, approved: boolean }) => {
      return apiRequest("POST", `/api/meals/${mealId}/approve`, { approved });
    },
    onSuccess: () => {
      toast({
        title: "Success",
        description: "Meal feedback submitted!",
      });
    },
  });

  const addCommentMutation = useMutation({
    mutationFn: async (comment: string) => {
      return apiRequest("POST", `/api/meal-plans/${mealPlan?.id}/comments`, {
        comment,
      });
    },
    onSuccess: () => {
      setNewComment("");
      toast({
        title: "Success",
        description: "Comment added successfully!",
      });
      queryClient.invalidateQueries({ queryKey: [`/api/meal-plans/${mealPlan?.id}/comments`] });
    },
  });

  const weekdays = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
  const mealTypes = [
    { type: "breakfast", label: "Breakfast", icon: Sun, iconStyle: "" },
    { type: "lunch", label: "Lunch", icon: Sun, iconStyle: "rotate-90" },
    { type: "dinner", label: "Dinner", icon: Moon, iconStyle: "" },
  ];

  const getMealForDay = (dayOfWeek: number, mealType: string) => {
    return mealPlan?.meals?.find(
      (meal: any) => meal.dayOfWeek === dayOfWeek && meal.mealType === mealType
    );
  };

  const getWeekDates = () => {
    const start = new Date(weekStartDate);
    return Array.from({ length: 7 }, (_, i) => {
      const date = new Date(start);
      date.setDate(start.getDate() + i);
      return date.getDate();
    });
  };

  const weekDates = getWeekDates();

  if (isLoading) {
    return (
      <div className="space-y-6">
        <div className="animate-pulse">
          <div className="h-8 bg-slate-200 rounded w-1/3 mb-2"></div>
          <div className="h-4 bg-slate-200 rounded w-1/2"></div>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center mb-6 space-y-4 sm:space-y-0">
        <div>
          <h2 className="text-2xl font-bold text-slate-900 mb-2">Weekly Meal Plan</h2>
          <p className="text-slate-600">Plan and approve meals for your household</p>
        </div>
        <div className="flex items-center space-x-4">
          <div className="flex items-center space-x-2 bg-white rounded-lg border border-slate-200 px-3 py-2">
            <Calendar className="h-4 w-4 text-slate-400" />
            <span className="text-sm font-medium text-slate-700">
              {new Date(weekStartDate).toLocaleDateString('en-US', { 
                month: 'short', 
                day: 'numeric',
                year: 'numeric'
              })} - {new Date(new Date(weekStartDate).getTime() + 6 * 24 * 60 * 60 * 1000).toLocaleDateString('en-US', { 
                month: 'short', 
                day: 'numeric'
              })}
            </span>
          </div>
          <Button 
            onClick={() => generatePlanMutation.mutate()}
            disabled={generatePlanMutation.isPending}
            className="bg-primary text-white hover:bg-primary/90"
          >
            <Wand2 className="h-4 w-4 mr-2" />
            {generatePlanMutation.isPending ? "Generating..." : "Regenerate Plan"}
          </Button>
        </div>
      </div>

      {/* Weekly Calendar */}
      <Card>
        <CardContent className="p-0">
          {/* Calendar Header */}
          <div className="grid grid-cols-8 bg-slate-50 border-b border-slate-200">
            <div className="p-4"></div>
            {weekdays.map((day, index) => (
              <div key={day} className={`p-4 text-center ${index === 5 ? 'bg-primary/5' : ''}`}>
                <div className={`text-xs font-medium uppercase tracking-wide ${index === 5 ? 'text-primary' : 'text-slate-500'}`}>
                  {day}
                </div>
                <div className={`text-lg font-semibold mt-1 ${index === 5 ? 'text-primary' : 'text-slate-900'}`}>
                  {weekDates[index]}
                </div>
              </div>
            ))}
          </div>

          {/* Meal Rows */}
          <div className="divide-y divide-slate-200">
            {mealTypes.map(({ type, label, icon: Icon, iconStyle }) => (
              <div key={type} className="grid grid-cols-8 min-h-[120px]">
                <div className="p-4 bg-slate-50 flex items-center">
                  <div className="text-center">
                    <Icon className={`h-5 w-5 text-${type === 'breakfast' ? 'secondary' : type === 'lunch' ? 'accent' : 'primary'} mb-1 mx-auto ${iconStyle}`} />
                    <div className="text-sm font-medium text-slate-900">{label}</div>
                  </div>
                </div>
                
                {Array.from({ length: 7 }, (_, dayIndex) => {
                  const meal = getMealForDay(dayIndex, type);
                  const isWeekend = dayIndex === 5 || dayIndex === 6;
                  
                  return (
                    <div key={dayIndex} className={`p-2 border-r border-slate-100 last:border-r-0 ${isWeekend ? 'bg-primary/5' : ''}`}>
                      {meal ? (
                        <div className="meal-card">
                          {meal.imageUrl && (
                            <img 
                              src={meal.imageUrl} 
                              alt={meal.name}
                              className="w-full h-16 object-cover rounded mb-2"
                            />
                          )}
                          <div>
                            <h4 className="text-xs font-medium text-slate-900 mb-1">
                              {meal.name}
                            </h4>
                            {meal.calories && (
                              <p className="text-xs text-slate-600">{meal.calories} cal</p>
                            )}
                            <div className="flex items-center justify-between mt-2">
                              <button 
                                onClick={() => approveMealMutation.mutate({ mealId: meal.id, approved: true })}
                                className="text-primary hover:text-primary/70 text-xs"
                              >
                                <ThumbsUp className="h-3 w-3" />
                              </button>
                              <button 
                                onClick={() => approveMealMutation.mutate({ mealId: meal.id, approved: false })}
                                className="text-slate-400 hover:text-slate-600 text-xs"
                              >
                                <ThumbsDown className="h-3 w-3" />
                              </button>
                            </div>
                          </div>
                        </div>
                      ) : (
                        <div className="h-full flex items-center justify-center text-slate-400">
                          <span className="text-xs">No meal planned</span>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* Meal Comments Section */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <MessageCircle className="h-5 w-5 text-accent" />
            Family Feedback
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {comments && comments.length > 0 ? (
            comments.map((comment: any) => (
              <div key={comment.id} className="flex items-start space-x-3 p-4 bg-slate-50 rounded-lg">
                <Avatar className="h-8 w-8">
                  <AvatarImage src={comment.user.profileImageUrl || ""} />
                  <AvatarFallback>
                    {comment.user.firstName?.[0]}{comment.user.lastName?.[0]}
                  </AvatarFallback>
                </Avatar>
                <div className="flex-1">
                  <div className="flex items-center space-x-2 mb-1">
                    <span className="font-medium text-slate-900">
                      {comment.user.firstName} {comment.user.lastName}
                    </span>
                    <span className="text-xs text-slate-500">
                      {new Date(comment.createdAt).toLocaleDateString()}
                    </span>
                    {comment.mealType && (
                      <Badge variant="outline" className="text-xs">
                        {comment.mealType}
                      </Badge>
                    )}
                  </div>
                  <p className="text-sm text-slate-700">{comment.comment}</p>
                </div>
              </div>
            ))
          ) : (
            <div className="text-center py-8 text-slate-500">
              <MessageCircle className="h-12 w-12 mx-auto mb-4 text-slate-300" />
              <p>No comments yet. Be the first to share your feedback!</p>
            </div>
          )}
          
          {/* Add Comment */}
          {mealPlan?.id && (
            <div className="pt-4 border-t border-slate-200">
              <div className="flex items-start space-x-3">
                <Avatar className="h-8 w-8">
                  <AvatarFallback>U</AvatarFallback>
                </Avatar>
                <div className="flex-1">
                  <Textarea
                    placeholder="Add your feedback about this week's meals..."
                    value={newComment}
                    onChange={(e) => setNewComment(e.target.value)}
                    className="resize-none"
                    rows={3}
                  />
                  <div className="flex items-center justify-end mt-2">
                    <Button 
                      onClick={() => addCommentMutation.mutate(newComment)}
                      disabled={!newComment.trim() || addCommentMutation.isPending}
                      size="sm"
                    >
                      <Send className="h-4 w-4 mr-2" />
                      Post Comment
                    </Button>
                  </div>
                </div>
              </div>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
