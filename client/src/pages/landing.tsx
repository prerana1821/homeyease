import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Home, Users, Calendar, ShoppingCart, Brain, CheckCircle } from "lucide-react";

export default function Landing() {
  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 to-slate-100">
      {/* Header */}
      <header className="bg-white shadow-sm border-b border-slate-200">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between items-center h-16">
            <div className="flex items-center space-x-2">
              <Home className="h-8 w-8 text-primary" />
              <h1 className="text-xl font-bold text-slate-900">HomeyEase</h1>
            </div>
            <Button 
              onClick={() => window.location.href = '/api/login'}
              className="bg-primary hover:bg-primary/90"
            >
              Get Started
            </Button>
          </div>
        </div>
      </header>

      {/* Hero Section */}
      <section className="relative py-20 lg:py-32">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="text-center">
            <h1 className="text-4xl lg:text-6xl font-bold text-slate-900 mb-6">
              AI-Powered Meal Planning &<br />
              <span className="text-primary">Grocery Management</span>
            </h1>
            <p className="text-xl text-slate-600 mb-8 max-w-3xl mx-auto">
              Perfect for shared households, families, and flatmates. Let AI handle your meal planning 
              while you focus on enjoying great food together.
            </p>
            <div className="flex flex-col sm:flex-row gap-4 justify-center">
              <Button 
                size="lg" 
                onClick={() => window.location.href = '/api/login'}
                className="bg-primary hover:bg-primary/90 text-lg px-8 py-4"
              >
                Start Planning Meals
              </Button>
              <Button 
                size="lg" 
                variant="outline"
                className="text-lg px-8 py-4"
              >
                Watch Demo
              </Button>
            </div>
          </div>
        </div>
      </section>

      {/* Features Section */}
      <section className="py-20 bg-white">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="text-center mb-16">
            <h2 className="text-3xl lg:text-4xl font-bold text-slate-900 mb-4">
              Everything Your Household Needs
            </h2>
            <p className="text-xl text-slate-600 max-w-2xl mx-auto">
              From meal planning to grocery tracking, HomeyEase makes shared household management effortless.
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8">
            <Card className="border-slate-200 hover:shadow-lg transition-shadow">
              <CardHeader>
                <Brain className="h-12 w-12 text-primary mb-4" />
                <CardTitle className="text-xl">AI Meal Planning</CardTitle>
                <CardDescription>
                  Generate personalized weekly meal plans based on dietary preferences, allergies, and nutrition goals.
                </CardDescription>
              </CardHeader>
            </Card>

            <Card className="border-slate-200 hover:shadow-lg transition-shadow">
              <CardHeader>
                <ShoppingCart className="h-12 w-12 text-secondary mb-4" />
                <CardTitle className="text-xl">Smart Inventory</CardTitle>
                <CardDescription>
                  Track your groceries with automatic low-stock alerts and expiration date reminders.
                </CardDescription>
              </CardHeader>
            </Card>

            <Card className="border-slate-200 hover:shadow-lg transition-shadow">
              <CardHeader>
                <Users className="h-12 w-12 text-accent mb-4" />
                <CardTitle className="text-xl">Family Profiles</CardTitle>
                <CardDescription>
                  Create individual profiles with dietary restrictions, preferences, and nutrition targets.
                </CardDescription>
              </CardHeader>
            </Card>

            <Card className="border-slate-200 hover:shadow-lg transition-shadow">
              <CardHeader>
                <Calendar className="h-12 w-12 text-primary mb-4" />
                <CardTitle className="text-xl">Calendar View</CardTitle>
                <CardDescription>
                  Visualize your weekly meals in an intuitive calendar format with approval system.
                </CardDescription>
              </CardHeader>
            </Card>

            <Card className="border-slate-200 hover:shadow-lg transition-shadow">
              <CardHeader>
                <CheckCircle className="h-12 w-12 text-secondary mb-4" />
                <CardTitle className="text-xl">Receipt Scanning</CardTitle>
                <CardDescription>
                  Upload grocery receipts to automatically update your inventory and track expenses.
                </CardDescription>
              </CardHeader>
            </Card>

            <Card className="border-slate-200 hover:shadow-lg transition-shadow">
              <CardHeader>
                <Brain className="h-12 w-12 text-accent mb-4" />
                <CardTitle className="text-xl">AI Insights</CardTitle>
                <CardDescription>
                  Get smart recommendations for shopping, nutrition improvements, and leftover management.
                </CardDescription>
              </CardHeader>
            </Card>
          </div>
        </div>
      </section>

      {/* How It Works */}
      <section className="py-20 bg-slate-50">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="text-center mb-16">
            <h2 className="text-3xl lg:text-4xl font-bold text-slate-900 mb-4">
              How HomeyEase Works
            </h2>
            <p className="text-xl text-slate-600">
              Get started in minutes and transform your household's meal planning
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
            <div className="text-center">
              <div className="bg-primary/10 w-16 h-16 rounded-full flex items-center justify-center mx-auto mb-6">
                <span className="text-2xl font-bold text-primary">1</span>
              </div>
              <h3 className="text-xl font-semibold text-slate-900 mb-4">Set Up Profiles</h3>
              <p className="text-slate-600">
                Create profiles for each household member with dietary preferences, restrictions, and goals.
              </p>
            </div>

            <div className="text-center">
              <div className="bg-secondary/10 w-16 h-16 rounded-full flex items-center justify-center mx-auto mb-6">
                <span className="text-2xl font-bold text-secondary">2</span>
              </div>
              <h3 className="text-xl font-semibold text-slate-900 mb-4">Generate Meal Plans</h3>
              <p className="text-slate-600">
                Let AI create personalized weekly meal plans that satisfy everyone's nutritional needs.
              </p>
            </div>

            <div className="text-center">
              <div className="bg-accent/10 w-16 h-16 rounded-full flex items-center justify-center mx-auto mb-6">
                <span className="text-2xl font-bold text-accent">3</span>
              </div>
              <h3 className="text-xl font-semibold text-slate-900 mb-4">Track & Improve</h3>
              <p className="text-slate-600">
                Monitor your inventory, get smart shopping lists, and receive AI insights for better nutrition.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* CTA Section */}
      <section className="py-20 bg-gradient-to-r from-primary to-accent">
        <div className="max-w-4xl mx-auto text-center px-4 sm:px-6 lg:px-8">
          <h2 className="text-3xl lg:text-4xl font-bold text-white mb-6">
            Ready to Transform Your Household?
          </h2>
          <p className="text-xl text-white/90 mb-8">
            Join thousands of families who've simplified their meal planning with AI
          </p>
          <Button 
            size="lg" 
            onClick={() => window.location.href = '/api/login'}
            className="bg-white text-primary hover:bg-slate-100 text-lg px-8 py-4"
          >
            Get Started Free
          </Button>
        </div>
      </section>

      {/* Footer */}
      <footer className="bg-slate-900 text-white py-12">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="text-center">
            <div className="flex items-center justify-center space-x-2 mb-4">
              <Home className="h-6 w-6" />
              <span className="text-xl font-bold">HomeyEase</span>
            </div>
            <p className="text-slate-400">
              AI-powered meal planning and grocery management for modern households
            </p>
          </div>
        </div>
      </footer>
    </div>
  );
}
