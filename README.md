
# HomeyEase 🍽️

> AI-powered household meal planning made effortless

HomeyEase is a collaborative meal planning application that brings AI intelligence to household food management. Plan meals together, generate smart shopping lists, and make dinner decisions stress-free with GPT-4 powered suggestions.

## ✨ Features

### 🤖 AI-Powered Meal Planning
- **Smart Meal Suggestions**: GPT-4 powered meal recommendations based on your household preferences
- **Dietary Restriction Compliance**: Automatic filtering for allergies, dietary needs, and preferences
- **Budget-Conscious Planning**: Cost-effective meal suggestions and ingredient optimization
- **Prep Time Optimization**: Meals planned around your available cooking time

### 👥 Collaborative Household Management
- **Multi-User Households**: Invite family members and roommates to collaborate
- **Preference Management**: Individual dietary restrictions and food preferences
- **Voting & Decision Making**: Democratic meal selection process
- **Role-Based Access**: Different permission levels for household members

### 📅 Smart Planning Tools
- **Weekly Meal Board**: Drag-and-drop meal planning with visual calendar
- **Auto-Generated Shopping Lists**: Ingredients automatically compiled from meal plans
- **Recipe Management**: Store and organize your favorite recipes
- **Meal History**: Track what you've eaten and discover patterns

### 🛒 Shopping Integration
- **Intelligent Shopping Lists**: Organized by store sections
- **Ingredient Consolidation**: Smart merging of duplicate items
- **Cost Estimation**: Budget tracking and meal cost analysis
- **Store Integration**: Optimized lists for different grocery stores

## 🚀 Getting Started

### Prerequisites
- Node.js 20+
- PostgreSQL database (Neon Database recommended)
- OpenAI API key

### Environment Setup

1. **Set up your OpenAI API key**:
   - Click on "Secrets" in the Replit sidebar
   - Add `OPENAI_API_KEY` with your OpenAI API key

2. **Configure your database**:
   - Set up a Neon Database account
   - Add your database URL to Secrets as `DATABASE_URL`

### Installation

1. **Install dependencies**:
   ```bash
   npm install
   ```

2. **Set up the database**:
   ```bash
   npm run db:push
   ```

3. **Start the development server**:
   ```bash
   npm run dev
   ```

The application will be available at `http://localhost:5000` (or your Replit URL).

## 🏗️ Technology Stack

### Frontend
- **React 18** with TypeScript for type-safe component development
- **Wouter** for lightweight client-side routing
- **TanStack Query** for server state management and caching
- **Shadcn/ui** component library built on Radix UI primitives
- **Tailwind CSS** with custom design tokens
- **React Beautiful DnD** for drag-and-drop meal planning
- **React Hook Form** with Zod validation

### Backend
- **Express.js** RESTful API with TypeScript
- **Drizzle ORM** for type-safe database operations
- **Neon Database** serverless PostgreSQL
- **OpenAI GPT-4** for AI-powered meal planning
- **Passport.js** for authentication
- **Express Session** with PostgreSQL storage

### Development Tools
- **Vite** for fast development and optimized builds
- **TypeScript** strict mode for type safety
- **ESLint** for code quality
- **PostCSS** with Autoprefixer

## 📁 Project Structure

```
├── client/                 # React frontend application
│   ├── src/
│   │   ├── components/     # Reusable UI components
│   │   ├── hooks/          # Custom React hooks
│   │   ├── lib/            # Utility functions
│   │   └── pages/          # Application pages
├── server/                 # Express.js backend
│   ├── services/           # AI and business logic services
│   ├── db.ts              # Database configuration
│   ├── routes.ts          # API route definitions
│   └── storage.ts         # Data access layer
├── shared/                 # Shared TypeScript schemas
└── docs/                  # Documentation
```

## 🗄️ Database Schema

HomeyEase uses four main entities:

- **`meals`** - Individual meal recipes with ingredients and dietary tags
- **`weekly_plans`** - Weekly meal schedules with day/slot assignments  
- **`household_preferences`** - Member profiles, dietary restrictions, and house rules
- **`shopping_lists`** - Auto-generated shopping lists linked to weekly plans

## 🎨 Design System

### Brand Colors
- **Primary**: Sage Green (#7C9885) - Health, harmony, and collaboration
- **Accent**: Orange (#F27149) - Appetite stimulation and warmth
- **Text**: Primary (#1F2722), Muted (#5B6A61)
- **UI**: Border (#E7ECEA), Background (#FAFAF8), Surface (#FFFFFF)

### Typography
- **Headings**: Poppins font family
- **Body**: Inter font family
- **Components**: Accessible Radix UI primitives

## 🚀 Deployment

### Replit Deployment (Recommended)

1. **Configure environment variables** in Replit Secrets:
   - `OPENAI_API_KEY`
   - `DATABASE_URL`
   - `NODE_ENV=production`

2. **Deploy**:
   ```bash
   npm run build
   ```

3. **Start production server**:
   ```bash
   npm start
   ```

## 📝 Scripts

- `npm run dev` - Start development server with hot reload
- `npm run build` - Build for production
- `npm start` - Start production server
- `npm run check` - Type checking with TypeScript
- `npm run db:push` - Push database schema changes

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🆘 Support

Having issues? Check out our [documentation](./docs) or create an issue in the repository.

## 🌟 Acknowledgments

- **OpenAI** for GPT-4 API powering our meal suggestions
- **Neon Database** for serverless PostgreSQL hosting
- **Radix UI** for accessible component primitives
- **Replit** for seamless development and deployment

---

**Made with ❤️ for busy households who want to eat well together**

*HomeyEase - Making household meal planning effortless since 2025*
