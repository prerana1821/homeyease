import { useState } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { Progress } from "@/components/ui/progress";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { useToast } from "@/hooks/use-toast";
import { apiRequest, queryClient } from "@/lib/queryClient";
import { isUnauthorizedError } from "@/lib/authUtils";
import { 
  UserPlus,
  Edit,
  Users,
  Target,
  Activity,
  TrendingUp,
  Heart,
  Shield
} from "lucide-react";

interface Profile {
  id: number;
  userId: string;
  householdId: number;
  dailyCalories: number;
  age: number;
  dietType: string;
  goal: string;
  restrictions: string[];
  preferences: string[];
  user: {
    id: string;
    email: string;
    firstName: string;
    lastName: string;
    profileImageUrl: string;
  };
}

export default function Profiles() {
  const { toast } = useToast();
  const [showAddProfile, setShowAddProfile] = useState(false);
  const [editingProfile, setEditingProfile] = useState<Profile | null>(null);
  const [newProfile, setNewProfile] = useState({
    dailyCalories: 2000,
    age: 25,
    dietType: "",
    goal: "",
    restrictions: [] as string[],
    preferences: [] as string[],
  });

  // For now, we'll assume user has at least one household
  const householdId = 1;

  const { data: profiles, isLoading } = useQuery({
    queryKey: [`/api/households/${householdId}/profiles`],
    enabled: !!householdId,
    retry: false,
  });

  const { data: members } = useQuery({
    queryKey: [`/api/households/${householdId}/members`],
    enabled: !!householdId,
    retry: false,
  });

  const createProfileMutation = useMutation({
    mutationFn: async (profileData: any) => {
      return apiRequest("POST", "/api/profiles", {
        ...profileData,
        householdId,
      });
    },
    onSuccess: () => {
      toast({
        title: "Success",
        description: "Profile created successfully!",
      });
      setShowAddProfile(false);
      setNewProfile({
        dailyCalories: 2000,
        age: 25,
        dietType: "",
        goal: "",
        restrictions: [],
        preferences: [],
      });
      queryClient.invalidateQueries({ queryKey: [`/api/households/${householdId}/profiles`] });
    },
    onError: (error) => {
      if (isUnauthorizedError(error)) {
        toast({
          title: "Unauthorized",
          description: "You are logged out. Logging in again...",
          variant: "destructive",
        });
        setTimeout(() => {
          window.location.href = "/api/login";
        }, 500);
        return;
      }
      toast({
        title: "Error",
        description: "Failed to create profile. Please try again.",
        variant: "destructive",
      });
    },
  });

  const updateProfileMutation = useMutation({
    mutationFn: async (profileData: any) => {
      return apiRequest("PUT", `/api/profiles/${householdId}/me`, profileData);
    },
    onSuccess: () => {
      toast({
        title: "Success",
        description: "Profile updated successfully!",
      });
      setEditingProfile(null);
      queryClient.invalidateQueries({ queryKey: [`/api/households/${householdId}/profiles`] });
    },
    onError: (error) => {
      if (isUnauthorizedError(error)) {
        toast({
          title: "Unauthorized",
          description: "You are logged out. Logging in again...",
          variant: "destructive",
        });
        setTimeout(() => {
          window.location.href = "/api/login";
        }, 500);
        return;
      }
      toast({
        title: "Error",
        description: "Failed to update profile. Please try again.",
        variant: "destructive",
      });
    },
  });

  const getDietTypeColor = (dietType: string) => {
    switch (dietType?.toLowerCase()) {
      case "vegetarian":
        return "bg-secondary/10 text-secondary";
      case "vegan":
        return "bg-green-100 text-green-600";
      case "keto":
        return "bg-purple-100 text-purple-600";
      case "paleo":
        return "bg-orange-100 text-orange-600";
      case "balanced":
        return "bg-primary/10 text-primary";
      case "high protein":
        return "bg-primary/10 text-primary";
      case "kid-friendly":
        return "bg-accent/10 text-accent";
      default:
        return "bg-slate-100 text-slate-600";
    }
  };

  const getGoalColor = (goal: string) => {
    switch (goal?.toLowerCase()) {
      case "weight loss":
        return "bg-accent/10 text-accent";
      case "muscle gain":
        return "bg-secondary/10 text-secondary";
      case "maintain weight":
        return "bg-primary/10 text-primary";
      case "growth":
        return "bg-primary/10 text-primary";
      default:
        return "bg-slate-100 text-slate-600";
    }
  };

  const addRestriction = (restriction: string) => {
    if (restriction && !newProfile.restrictions.includes(restriction)) {
      setNewProfile({
        ...newProfile,
        restrictions: [...newProfile.restrictions, restriction]
      });
    }
  };

  const removeRestriction = (restriction: string) => {
    setNewProfile({
      ...newProfile,
      restrictions: newProfile.restrictions.filter(r => r !== restriction)
    });
  };

  const addPreference = (preference: string) => {
    if (preference && !newProfile.preferences.includes(preference)) {
      setNewProfile({
        ...newProfile,
        preferences: [...newProfile.preferences, preference]
      });
    }
  };

  const removePreference = (preference: string) => {
    setNewProfile({
      ...newProfile,
      preferences: newProfile.preferences.filter(p => p !== preference)
    });
  };

  // Mock progress data (in a real app, this would come from the API)
  const getMockProgress = (profile: Profile) => {
    return {
      calories: Math.floor(profile.dailyCalories * 0.85),
      caloriesTarget: profile.dailyCalories,
      protein: Math.floor(120 + Math.random() * 40),
      proteinTarget: Math.floor(profile.dailyCalories * 0.15 / 4), // 15% of calories from protein
      otherNutrient: profile.dietType === "Vegetarian" ? "Iron" : "Vitamin D",
      otherValue: Math.floor(12 + Math.random() * 8),
      otherTarget: 18,
    };
  };

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
          <h2 className="text-2xl font-bold text-slate-900 mb-2">Family Profiles</h2>
          <p className="text-slate-600">Manage dietary preferences and nutrition goals</p>
        </div>
        <Dialog open={showAddProfile} onOpenChange={setShowAddProfile}>
          <DialogTrigger asChild>
            <Button className="bg-primary text-white hover:bg-primary/90">
              <UserPlus className="h-4 w-4 mr-2" />
              Add Member
            </Button>
          </DialogTrigger>
          <DialogContent className="max-w-2xl">
            <DialogHeader>
              <DialogTitle>Add Family Member Profile</DialogTitle>
            </DialogHeader>
            <div className="space-y-4 max-h-96 overflow-y-auto">
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <Label htmlFor="calories">Daily Calories</Label>
                  <Input
                    id="calories"
                    type="number"
                    value={newProfile.dailyCalories}
                    onChange={(e) => setNewProfile({ ...newProfile, dailyCalories: parseInt(e.target.value) || 2000 })}
                  />
                </div>
                <div>
                  <Label htmlFor="age">Age</Label>
                  <Input
                    id="age"
                    type="number"
                    value={newProfile.age}
                    onChange={(e) => setNewProfile({ ...newProfile, age: parseInt(e.target.value) || 25 })}
                  />
                </div>
              </div>
              
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <Label htmlFor="dietType">Diet Type</Label>
                  <Select value={newProfile.dietType} onValueChange={(value) => setNewProfile({ ...newProfile, dietType: value })}>
                    <SelectTrigger>
                      <SelectValue placeholder="Select diet type" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="Balanced">Balanced</SelectItem>
                      <SelectItem value="Vegetarian">Vegetarian</SelectItem>
                      <SelectItem value="Vegan">Vegan</SelectItem>
                      <SelectItem value="Keto">Keto</SelectItem>
                      <SelectItem value="Paleo">Paleo</SelectItem>
                      <SelectItem value="High Protein">High Protein</SelectItem>
                      <SelectItem value="Kid-Friendly">Kid-Friendly</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <Label htmlFor="goal">Goal</Label>
                  <Select value={newProfile.goal} onValueChange={(value) => setNewProfile({ ...newProfile, goal: value })}>
                    <SelectTrigger>
                      <SelectValue placeholder="Select goal" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="Maintain Weight">Maintain Weight</SelectItem>
                      <SelectItem value="Weight Loss">Weight Loss</SelectItem>
                      <SelectItem value="Muscle Gain">Muscle Gain</SelectItem>
                      <SelectItem value="Growth">Growth</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>

              <div>
                <Label>Dietary Restrictions</Label>
                <div className="flex flex-wrap gap-2 mb-2">
                  {newProfile.restrictions.map((restriction) => (
                    <Badge key={restriction} variant="destructive" className="cursor-pointer" onClick={() => removeRestriction(restriction)}>
                      {restriction} ×
                    </Badge>
                  ))}
                </div>
                <Select onValueChange={addRestriction}>
                  <SelectTrigger>
                    <SelectValue placeholder="Add restriction" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="No Meat">No Meat</SelectItem>
                    <SelectItem value="No Dairy">No Dairy</SelectItem>
                    <SelectItem value="Nut Allergy">Nut Allergy</SelectItem>
                    <SelectItem value="Gluten Free">Gluten Free</SelectItem>
                    <SelectItem value="Lactose Sensitive">Lactose Sensitive</SelectItem>
                    <SelectItem value="Shellfish Allergy">Shellfish Allergy</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              <div>
                <Label>Food Preferences</Label>
                <div className="flex flex-wrap gap-2 mb-2">
                  {newProfile.preferences.map((preference) => (
                    <Badge key={preference} variant="secondary" className="cursor-pointer" onClick={() => removePreference(preference)}>
                      {preference} ×
                    </Badge>
                  ))}
                </div>
                <Select onValueChange={addPreference}>
                  <SelectTrigger>
                    <SelectValue placeholder="Add preference" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="Mediterranean">Mediterranean</SelectItem>
                    <SelectItem value="Asian">Asian</SelectItem>
                    <SelectItem value="Mexican">Mexican</SelectItem>
                    <SelectItem value="Italian">Italian</SelectItem>
                    <SelectItem value="Seafood">Seafood</SelectItem>
                    <SelectItem value="Vegetables">Vegetables</SelectItem>
                    <SelectItem value="Lean Meats">Lean Meats</SelectItem>
                    <SelectItem value="Plant-based">Plant-based</SelectItem>
                    <SelectItem value="Quinoa">Quinoa</SelectItem>
                    <SelectItem value="Legumes">Legumes</SelectItem>
                    <SelectItem value="Pasta">Pasta</SelectItem>
                    <SelectItem value="Chicken">Chicken</SelectItem>
                    <SelectItem value="Fruits">Fruits</SelectItem>
                    <SelectItem value="Eggs">Eggs</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              <div className="flex justify-end space-x-2 pt-4">
                <Button variant="outline" onClick={() => setShowAddProfile(false)}>
                  Cancel
                </Button>
                <Button 
                  onClick={() => createProfileMutation.mutate(newProfile)}
                  disabled={!newProfile.dietType || !newProfile.goal || createProfileMutation.isPending}
                >
                  {createProfileMutation.isPending ? "Creating..." : "Create Profile"}
                </Button>
              </div>
            </div>
          </DialogContent>
        </Dialog>
      </div>

      {/* Profiles Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8">
        {profiles && profiles.length > 0 ? (
          profiles.map((profile: Profile) => {
            const progress = getMockProgress(profile);
            const calorieProgress = (progress.calories / progress.caloriesTarget) * 100;
            const proteinProgress = (progress.protein / progress.proteinTarget) * 100;
            
            return (
              <Card key={profile.id}>
                <CardContent className="p-6">
                  <div className="flex items-center space-x-4 mb-6">
                    <Avatar className="h-16 w-16">
                      <AvatarImage src={profile.user.profileImageUrl || ""} />
                      <AvatarFallback>
                        {profile.user.firstName?.[0]}{profile.user.lastName?.[0]}
                      </AvatarFallback>
                    </Avatar>
                    <div className="flex-1">
                      <h3 className="text-lg font-semibold text-slate-900">
                        {profile.user.firstName} {profile.user.lastName}
                      </h3>
                      <p className="text-slate-600">
                        {members?.find((m: any) => m.userId === profile.userId)?.role || "Member"}
                      </p>
                      <div className="flex items-center space-x-2 mt-1">
                        <Badge className={getDietTypeColor(profile.dietType)}>
                          {profile.dietType}
                        </Badge>
                        <Badge className={getGoalColor(profile.goal)}>
                          {profile.goal}
                        </Badge>
                      </div>
                    </div>
                    <Button variant="ghost" size="sm" onClick={() => setEditingProfile(profile)}>
                      <Edit className="h-4 w-4" />
                    </Button>
                  </div>

                  <div className="grid grid-cols-2 gap-4 mb-6">
                    <div className="text-center p-3 bg-slate-50 rounded-lg">
                      <p className="text-2xl font-bold text-slate-900">{profile.dailyCalories?.toLocaleString()}</p>
                      <p className="text-xs text-slate-600">Daily Calories</p>
                    </div>
                    <div className="text-center p-3 bg-slate-50 rounded-lg">
                      <p className="text-2xl font-bold text-slate-900">{profile.age}</p>
                      <p className="text-xs text-slate-600">Age</p>
                    </div>
                  </div>

                  <div className="space-y-4">
                    {/* Dietary Restrictions */}
                    <div>
                      <h4 className="text-sm font-medium text-slate-900 mb-2 flex items-center gap-2">
                        <Shield className="h-4 w-4" />
                        Dietary Restrictions
                      </h4>
                      <div className="flex flex-wrap gap-2">
                        {profile.restrictions && profile.restrictions.length > 0 ? (
                          profile.restrictions.map((restriction) => (
                            <Badge key={restriction} variant="destructive" className="text-xs">
                              {restriction}
                            </Badge>
                          ))
                        ) : (
                          <Badge variant="outline" className="text-xs text-slate-500">
                            None
                          </Badge>
                        )}
                      </div>
                    </div>

                    {/* Food Preferences */}
                    <div>
                      <h4 className="text-sm font-medium text-slate-900 mb-2 flex items-center gap-2">
                        <Heart className="h-4 w-4" />
                        Preferred Foods
                      </h4>
                      <div className="flex flex-wrap gap-2">
                        {profile.preferences && profile.preferences.length > 0 ? (
                          profile.preferences.slice(0, 3).map((preference) => (
                            <Badge key={preference} variant="secondary" className="text-xs">
                              {preference}
                            </Badge>
                          ))
                        ) : (
                          <Badge variant="outline" className="text-xs text-slate-500">
                            None specified
                          </Badge>
                        )}
                      </div>
                    </div>

                    {/* Progress */}
                    <div>
                      <h4 className="text-sm font-medium text-slate-900 mb-2 flex items-center gap-2">
                        <Activity className="h-4 w-4" />
                        This Week's Progress
                      </h4>
                      <div className="space-y-2">
                        <div className="flex justify-between text-sm">
                          <span className="text-slate-600">Calories</span>
                          <span className="font-medium">
                            {progress.calories.toLocaleString()} / {progress.caloriesTarget.toLocaleString()}
                          </span>
                        </div>
                        <Progress value={calorieProgress} className="h-2" />
                        
                        <div className="flex justify-between text-sm">
                          <span className="text-slate-600">Protein</span>
                          <span className={`font-medium ${proteinProgress >= 100 ? 'text-primary' : 'text-slate-900'}`}>
                            {progress.protein}g / {progress.proteinTarget}g
                          </span>
                        </div>
                        <Progress value={Math.min(100, proteinProgress)} className="h-2" />
                      </div>
                    </div>
                  </div>
                </CardContent>
              </Card>
            );
          })
        ) : (
          <div className="col-span-full text-center py-12">
            <Users className="h-12 w-12 mx-auto mb-4 text-slate-300" />
            <h3 className="text-lg font-medium text-slate-900 mb-2">No profiles yet</h3>
            <p className="text-slate-600 mb-4">
              Create profiles for each household member to get personalized meal plans
            </p>
            <Button onClick={() => setShowAddProfile(true)}>
              <UserPlus className="h-4 w-4 mr-2" />
              Add Member
            </Button>
          </div>
        )}
      </div>

      {/* Household Nutrition Summary */}
      {profiles && profiles.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <TrendingUp className="h-5 w-5 text-primary" />
              Household Nutrition Summary
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
              <div className="text-center p-4 bg-gradient-to-br from-primary/5 to-accent/5 rounded-lg">
                <div className="text-3xl font-bold text-primary mb-2">87%</div>
                <p className="text-sm font-medium text-slate-900">Weekly Goal Achievement</p>
                <p className="text-xs text-slate-600 mt-1">Above household target</p>
              </div>
              <div className="text-center p-4 bg-gradient-to-br from-secondary/5 to-primary/5 rounded-lg">
                <div className="text-3xl font-bold text-secondary mb-2">$52</div>
                <p className="text-sm font-medium text-slate-900">Avg. Cost per Person</p>
                <p className="text-xs text-slate-600 mt-1">This week's groceries</p>
              </div>
              <div className="text-center p-4 bg-gradient-to-br from-accent/5 to-secondary/5 rounded-lg">
                <div className="text-3xl font-bold text-accent mb-2">92%</div>
                <p className="text-sm font-medium text-slate-900">Meal Plan Satisfaction</p>
                <p className="text-xs text-slate-600 mt-1">Based on feedback</p>
              </div>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
