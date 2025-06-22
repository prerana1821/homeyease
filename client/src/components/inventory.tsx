import { useState } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { useToast } from "@/hooks/use-toast";
import { apiRequest, queryClient } from "@/lib/queryClient";
import { isUnauthorizedError } from "@/lib/authUtils";
import { 
  Camera,
  Plus,
  Edit,
  Trash2,
  Apple,
  Wheat,
  Fish,
  Egg,
  Carrot,
  ShoppingCart,
  AlertTriangle,
  Calendar,
  DollarSign,
  X,
  Share
} from "lucide-react";

interface InventoryItem {
  id: number;
  name: string;
  category: string;
  quantity: string;
  unit: string;
  cost: string;
  expiryDate: string;
  lowStockThreshold: number;
}

interface ShoppingListItem {
  id: number;
  name: string;
  reason: string;
  estimatedCost: string;
  store: string;
  completed: boolean;
}

export default function Inventory() {
  const { toast } = useToast();
  const [activeCategory, setActiveCategory] = useState("all");
  const [showAddItem, setShowAddItem] = useState(false);
  const [showReceiptUpload, setShowReceiptUpload] = useState(false);
  const [receiptText, setReceiptText] = useState("");
  const [newItem, setNewItem] = useState({
    name: "",
    category: "",
    quantity: "",
    unit: "",
    cost: "",
    expiryDate: "",
    lowStockThreshold: 0,
  });

  // For now, we'll assume user has at least one household
  const householdId = 1;

  const { data: inventory, isLoading: inventoryLoading } = useQuery({
    queryKey: [`/api/households/${householdId}/inventory`, activeCategory],
    enabled: !!householdId,
    retry: false,
  });

  const { data: shoppingList, isLoading: shoppingLoading } = useQuery({
    queryKey: [`/api/households/${householdId}/shopping-list`],
    enabled: !!householdId,
    retry: false,
  });

  const addItemMutation = useMutation({
    mutationFn: async (itemData: any) => {
      return apiRequest("POST", "/api/inventory", {
        ...itemData,
        householdId,
        cost: parseFloat(itemData.cost || "0"),
      });
    },
    onSuccess: () => {
      toast({
        title: "Success",
        description: "Item added to inventory successfully!",
      });
      setShowAddItem(false);
      setNewItem({
        name: "",
        category: "",
        quantity: "",
        unit: "",
        cost: "",
        expiryDate: "",
        lowStockThreshold: 0,
      });
      queryClient.invalidateQueries({ queryKey: [`/api/households/${householdId}/inventory`] });
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
        description: "Failed to add item. Please try again.",
        variant: "destructive",
      });
    },
  });

  const analyzeReceiptMutation = useMutation({
    mutationFn: async (text: string) => {
      return apiRequest("POST", "/api/receipts/analyze", { receiptText: text });
    },
    onSuccess: (data) => {
      toast({
        title: "Success",
        description: `Receipt analyzed! Found ${data.items?.length || 0} items.`,
      });
      // Here you could auto-add the items or show them for review
      setShowReceiptUpload(false);
      setReceiptText("");
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
        description: "Failed to analyze receipt. Please try again.",
        variant: "destructive",
      });
    },
  });

  const updateShoppingItemMutation = useMutation({
    mutationFn: async ({ id, completed }: { id: number, completed: boolean }) => {
      return apiRequest("PUT", `/api/shopping-list/${id}`, { completed });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: [`/api/households/${householdId}/shopping-list`] });
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
    },
  });

  const getCategoryIcon = (category: string) => {
    switch (category.toLowerCase()) {
      case "fresh produce":
        return Apple;
      case "bakery":
        return Wheat;
      case "seafood":
        return Fish;
      case "dairy":
        return Egg;
      default:
        return Carrot;
    }
  };

  const getCategoryColor = (category: string) => {
    switch (category.toLowerCase()) {
      case "fresh produce":
        return "text-primary";
      case "bakery":
        return "text-secondary";
      case "seafood":
        return "text-accent";
      case "dairy":
        return "text-secondary";
      default:
        return "text-primary";
    }
  };

  const getStockLevel = (item: InventoryItem) => {
    if (!item.lowStockThreshold) return 100;
    const quantity = parseInt(item.quantity || "0");
    return Math.min(100, (quantity / item.lowStockThreshold) * 100);
  };

  const getStockColor = (level: number) => {
    if (level <= 25) return "bg-red-500";
    if (level <= 50) return "bg-secondary";
    return "bg-primary";
  };

  const isExpiringSoon = (expiryDate: string) => {
    if (!expiryDate) return false;
    const expiry = new Date(expiryDate);
    const threeDaysFromNow = new Date();
    threeDaysFromNow.setDate(threeDaysFromNow.getDate() + 3);
    return expiry <= threeDaysFromNow;
  };

  const filteredInventory = inventory?.filter((item: InventoryItem) => {
    if (activeCategory === "all") return true;
    if (activeCategory === "low-stock") {
      return getStockLevel(item) <= 25;
    }
    if (activeCategory === "expiring") {
      return isExpiringSoon(item.expiryDate);
    }
    if (activeCategory === "fresh") {
      return item.category?.toLowerCase() === "fresh produce";
    }
    return true;
  }) || [];

  const categories = [
    { id: "all", label: "All Items", count: inventory?.length || 0 },
    { id: "low-stock", label: "Low Stock", count: inventory?.filter((item: InventoryItem) => getStockLevel(item) <= 25).length || 0 },
    { id: "expiring", label: "Expiring Soon", count: inventory?.filter((item: InventoryItem) => isExpiringSoon(item.expiryDate)).length || 0 },
    { id: "fresh", label: "Fresh Produce", count: inventory?.filter((item: InventoryItem) => item.category?.toLowerCase() === "fresh produce").length || 0 },
  ];

  if (inventoryLoading) {
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
          <h2 className="text-2xl font-bold text-slate-900 mb-2">Kitchen Inventory</h2>
          <p className="text-slate-600">Track your groceries and get low-stock alerts</p>
        </div>
        <div className="flex items-center space-x-4">
          <Dialog open={showReceiptUpload} onOpenChange={setShowReceiptUpload}>
            <DialogTrigger asChild>
              <Button variant="outline" className="bg-secondary text-white hover:bg-secondary/90">
                <Camera className="h-4 w-4 mr-2" />
                Upload Receipt
              </Button>
            </DialogTrigger>
            <DialogContent>
              <DialogHeader>
                <DialogTitle>Upload Receipt</DialogTitle>
              </DialogHeader>
              <div className="space-y-4">
                <div>
                  <Label htmlFor="receipt">Receipt Text</Label>
                  <Textarea
                    id="receipt"
                    placeholder="Paste your receipt text here or describe the items you bought..."
                    value={receiptText}
                    onChange={(e) => setReceiptText(e.target.value)}
                    rows={6}
                  />
                </div>
                <div className="flex justify-end space-x-2">
                  <Button variant="outline" onClick={() => setShowReceiptUpload(false)}>
                    Cancel
                  </Button>
                  <Button 
                    onClick={() => analyzeReceiptMutation.mutate(receiptText)}
                    disabled={!receiptText.trim() || analyzeReceiptMutation.isPending}
                  >
                    {analyzeReceiptMutation.isPending ? "Analyzing..." : "Analyze Receipt"}
                  </Button>
                </div>
              </div>
            </DialogContent>
          </Dialog>

          <Dialog open={showAddItem} onOpenChange={setShowAddItem}>
            <DialogTrigger asChild>
              <Button className="bg-primary text-white hover:bg-primary/90">
                <Plus className="h-4 w-4 mr-2" />
                Add Item
              </Button>
            </DialogTrigger>
            <DialogContent>
              <DialogHeader>
                <DialogTitle>Add Inventory Item</DialogTitle>
              </DialogHeader>
              <div className="space-y-4">
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <Label htmlFor="name">Item Name</Label>
                    <Input
                      id="name"
                      value={newItem.name}
                      onChange={(e) => setNewItem({ ...newItem, name: e.target.value })}
                      placeholder="e.g., Organic Apples"
                    />
                  </div>
                  <div>
                    <Label htmlFor="category">Category</Label>
                    <Select value={newItem.category} onValueChange={(value) => setNewItem({ ...newItem, category: value })}>
                      <SelectTrigger>
                        <SelectValue placeholder="Select category" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="Fresh Produce">Fresh Produce</SelectItem>
                        <SelectItem value="Dairy">Dairy</SelectItem>
                        <SelectItem value="Meat">Meat</SelectItem>
                        <SelectItem value="Seafood">Seafood</SelectItem>
                        <SelectItem value="Bakery">Bakery</SelectItem>
                        <SelectItem value="Grains">Grains</SelectItem>
                        <SelectItem value="Pantry">Pantry</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                </div>
                <div className="grid grid-cols-3 gap-4">
                  <div>
                    <Label htmlFor="quantity">Quantity</Label>
                    <Input
                      id="quantity"
                      value={newItem.quantity}
                      onChange={(e) => setNewItem({ ...newItem, quantity: e.target.value })}
                      placeholder="6"
                    />
                  </div>
                  <div>
                    <Label htmlFor="unit">Unit</Label>
                    <Input
                      id="unit"
                      value={newItem.unit}
                      onChange={(e) => setNewItem({ ...newItem, unit: e.target.value })}
                      placeholder="pieces"
                    />
                  </div>
                  <div>
                    <Label htmlFor="cost">Cost ($)</Label>
                    <Input
                      id="cost"
                      type="number"
                      step="0.01"
                      value={newItem.cost}
                      onChange={(e) => setNewItem({ ...newItem, cost: e.target.value })}
                      placeholder="4.99"
                    />
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <Label htmlFor="expiry">Expiry Date</Label>
                    <Input
                      id="expiry"
                      type="date"
                      value={newItem.expiryDate}
                      onChange={(e) => setNewItem({ ...newItem, expiryDate: e.target.value })}
                    />
                  </div>
                  <div>
                    <Label htmlFor="threshold">Low Stock Alert</Label>
                    <Input
                      id="threshold"
                      type="number"
                      value={newItem.lowStockThreshold}
                      onChange={(e) => setNewItem({ ...newItem, lowStockThreshold: parseInt(e.target.value) || 0 })}
                      placeholder="2"
                    />
                  </div>
                </div>
                <div className="flex justify-end space-x-2">
                  <Button variant="outline" onClick={() => setShowAddItem(false)}>
                    Cancel
                  </Button>
                  <Button 
                    onClick={() => addItemMutation.mutate(newItem)}
                    disabled={!newItem.name || addItemMutation.isPending}
                  >
                    {addItemMutation.isPending ? "Adding..." : "Add Item"}
                  </Button>
                </div>
              </div>
            </DialogContent>
          </Dialog>
        </div>
      </div>

      {/* Category Tabs */}
      <div className="flex space-x-6 mb-6 border-b border-slate-200">
        {categories.map((category) => (
          <button
            key={category.id}
            className={`category-tab ${activeCategory === category.id ? "active" : ""}`}
            onClick={() => setActiveCategory(category.id)}
          >
            {category.label}
            <Badge variant="outline" className="ml-2">
              {category.count}
            </Badge>
          </button>
        ))}
      </div>

      {/* Inventory Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4 mb-8">
        {filteredInventory.length > 0 ? (
          filteredInventory.map((item: InventoryItem) => {
            const IconComponent = getCategoryIcon(item.category);
            const stockLevel = getStockLevel(item);
            const isLowStock = stockLevel <= 25;
            const isExpiring = isExpiringSoon(item.expiryDate);
            
            return (
              <Card 
                key={item.id} 
                className={`hover:shadow-md transition-shadow ${isExpiring ? 'border-red-200' : isLowStock ? 'border-secondary/20' : ''}`}
              >
                <CardContent className="p-4">
                  <div className="flex items-center justify-between mb-3">
                    <div className="flex items-center space-x-2">
                      <div className="w-10 h-10 bg-gradient-to-br from-primary/10 to-accent/10 rounded-lg flex items-center justify-center">
                        <IconComponent className={`h-5 w-5 ${getCategoryColor(item.category)}`} />
                      </div>
                      <div>
                        <h4 className="font-medium text-slate-900">{item.name}</h4>
                        <p className="text-xs text-slate-500">{item.category}</p>
                      </div>
                    </div>
                    <Badge 
                      variant="outline" 
                      className={isLowStock ? "bg-secondary/10 text-secondary" : isExpiring ? "bg-red-100 text-red-600" : "bg-primary/10 text-primary"}
                    >
                      {item.quantity} {item.unit}
                    </Badge>
                  </div>
                  
                  <div className="space-y-2">
                    <div className="flex justify-between text-sm">
                      <span className="text-slate-600">Expires</span>
                      <span className={`font-medium ${isExpiring ? 'text-red-600' : 'text-slate-900'}`}>
                        {item.expiryDate ? new Date(item.expiryDate).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) : 'N/A'}
                      </span>
                    </div>
                    <div className="flex justify-between text-sm">
                      <span className="text-slate-600">Cost</span>
                      <span className="font-medium text-slate-900">${parseFloat(item.cost || "0").toFixed(2)}</span>
                    </div>
                    <div className="w-full bg-slate-100 rounded-full h-2">
                      <div 
                        className={`h-2 rounded-full ${getStockColor(stockLevel)}`}
                        style={{ width: `${stockLevel}%` }}
                      ></div>
                    </div>
                  </div>
                  
                  <div className="flex justify-between items-center mt-3">
                    <Button variant="ghost" size="sm" className="text-slate-400 hover:text-slate-600">
                      <Edit className="h-4 w-4 mr-1" />
                      Edit
                    </Button>
                    <Button variant="ghost" size="sm" className="text-accent hover:text-accent/70">
                      <Plus className="h-4 w-4 mr-1" />
                      Restock
                    </Button>
                  </div>
                </CardContent>
              </Card>
            );
          })
        ) : (
          <div className="col-span-full text-center py-12">
            <ShoppingCart className="h-12 w-12 mx-auto mb-4 text-slate-300" />
            <h3 className="text-lg font-medium text-slate-900 mb-2">No items found</h3>
            <p className="text-slate-600 mb-4">
              {activeCategory === "all" 
                ? "Start by adding some items to your inventory" 
                : `No items in the ${categories.find(c => c.id === activeCategory)?.label.toLowerCase()} category`}
            </p>
            <Button onClick={() => setShowAddItem(true)}>
              <Plus className="h-4 w-4 mr-2" />
              Add Item
            </Button>
          </div>
        )}
      </div>

      {/* Shopping List */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle className="flex items-center gap-2">
              <List className="h-5 w-5 text-secondary" />
              Smart Shopping List
            </CardTitle>
            <Button variant="ghost" size="sm" className="text-primary hover:text-primary/70">
              <Share className="h-4 w-4 mr-1" />
              Share List
            </Button>
          </div>
        </CardHeader>
        <CardContent className="space-y-3">
          {shoppingLoading ? (
            <div className="space-y-3">
              {[1, 2, 3].map((i) => (
                <div key={i} className="animate-pulse">
                  <div className="h-16 bg-slate-100 rounded-lg"></div>
                </div>
              ))}
            </div>
          ) : shoppingList && shoppingList.length > 0 ? (
            shoppingList.map((item: ShoppingListItem) => (
              <div key={item.id} className="flex items-center space-x-3 p-3 bg-slate-50 rounded-lg">
                <input 
                  type="checkbox" 
                  checked={item.completed}
                  onChange={(e) => updateShoppingItemMutation.mutate({ id: item.id, completed: e.target.checked })}
                  className="rounded text-primary focus:ring-primary/20" 
                />
                <div className="flex-1">
                  <h4 className={`font-medium ${item.completed ? 'line-through text-slate-500' : 'text-slate-900'}`}>
                    {item.name}
                  </h4>
                  <p className="text-xs text-slate-500">{item.reason}</p>
                </div>
                <div className="text-right">
                  <p className="text-sm font-medium text-slate-900">
                    ${parseFloat(item.estimatedCost || "0").toFixed(2)}
                  </p>
                  <p className="text-xs text-slate-500">{item.store}</p>
                </div>
                <Button variant="ghost" size="sm" className="text-slate-400 hover:text-slate-600">
                  <X className="h-4 w-4" />
                </Button>
              </div>
            ))
          ) : (
            <div className="text-center py-8 text-slate-500">
              <ShoppingCart className="h-12 w-12 mx-auto mb-4 text-slate-300" />
              <p>Your shopping list is empty. Low stock items will appear here automatically.</p>
            </div>
          )}
          
          {shoppingList && shoppingList.length > 0 && (
            <div className="flex items-center justify-between mt-4 pt-4 border-t border-slate-200">
              <div className="text-sm text-slate-600">
                <span className="font-medium">
                  Estimated Total: ${shoppingList.reduce((total: number, item: ShoppingListItem) => 
                    total + parseFloat(item.estimatedCost || "0"), 0).toFixed(2)}
                </span>
              </div>
              <Button size="sm">
                Generate Shopping Plan
              </Button>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
