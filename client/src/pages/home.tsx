import { useState, useEffect } from "react";
import { useAuth } from "@/hooks/useAuth";
import { useToast } from "@/hooks/use-toast";
import { isUnauthorizedError } from "@/lib/authUtils";
import Navigation from "@/components/navigation";
import Dashboard from "@/components/dashboard";
import MealPlan from "@/components/meal-plan";
import Inventory from "@/components/inventory";
import Profiles from "@/components/profiles";

export default function Home() {
  const { toast } = useToast();
  const { isAuthenticated, isLoading } = useAuth();
  const [activeSection, setActiveSection] = useState("dashboard");

  // Redirect to home if not authenticated
  useEffect(() => {
    if (!isLoading && !isAuthenticated) {
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
  }, [isAuthenticated, isLoading, toast]);

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="animate-spin rounded-full h-32 w-32 border-b-2 border-primary"></div>
      </div>
    );
  }

  if (!isAuthenticated) {
    return null;
  }

  const renderSection = () => {
    switch (activeSection) {
      case "dashboard":
        return <Dashboard />;
      case "meal-plan":
        return <MealPlan />;
      case "inventory":
        return <Inventory />;
      case "profiles":
        return <Profiles />;
      default:
        return <Dashboard />;
    }
  };

  return (
    <div className="min-h-screen bg-slate-50">
      <Navigation activeSection={activeSection} onSectionChange={setActiveSection} />
      
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6 pb-20 md:pb-6">
        {renderSection()}
      </main>

      {/* Mobile Navigation */}
      <nav className="md:hidden bg-white border-t border-slate-200 fixed bottom-0 left-0 right-0 z-50">
        <div className="flex justify-around py-2">
          <button 
            className={`mobile-nav-btn ${activeSection === "dashboard" ? "active" : ""}`}
            onClick={() => setActiveSection("dashboard")}
          >
            <i className="fas fa-chart-line text-lg"></i>
            <span className="text-xs">Dashboard</span>
          </button>
          <button 
            className={`mobile-nav-btn ${activeSection === "meal-plan" ? "active" : ""}`}
            onClick={() => setActiveSection("meal-plan")}
          >
            <i className="fas fa-calendar-alt text-lg"></i>
            <span className="text-xs">Meal Plan</span>
          </button>
          <button 
            className={`mobile-nav-btn ${activeSection === "inventory" ? "active" : ""}`}
            onClick={() => setActiveSection("inventory")}
          >
            <i className="fas fa-boxes text-lg"></i>
            <span className="text-xs">Inventory</span>
          </button>
          <button 
            className={`mobile-nav-btn ${activeSection === "profiles" ? "active" : ""}`}
            onClick={() => setActiveSection("profiles")}
          >
            <i className="fas fa-users text-lg"></i>
            <span className="text-xs">Profiles</span>
          </button>
        </div>
      </nav>
    </div>
  );
}
