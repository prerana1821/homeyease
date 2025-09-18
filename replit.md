# Mambo - WhatsApp Meal Planning Bot

## Project Overview
This is a Python FastAPI-based WhatsApp meal planning bot called "Mambo" that provides AI-powered meal suggestions and planning through WhatsApp integration. The bot can process text messages and images (ingredient detection) to provide personalized meal recommendations.

## Recent Changes
- **2025-09-18**: Initial setup for Replit environment
- Configured uv package manager for dependency management
- Set up FastAPI server to run on port 5000 with proper host configuration

## Architecture
- **Backend**: FastAPI Python web server
- **Database**: Supabase (PostgreSQL with additional features)
- **Integrations**: 
  - WhatsApp Cloud API for messaging
  - Twilio as backup/alternative messaging channel
  - Google Cloud Vision for image processing
  - OpenAI for AI-powered responses
- **Key Components**:
  - Webhook endpoints for message handling
  - Intent classification and message processing
  - Meal recommendation service
  - User onboarding flows

## Project Structure
```
app/
├── api/          # Webhook endpoints (WhatsApp, Twilio)
├── config/       # Settings and Supabase configuration
├── models/       # Database models
├── services/     # Business logic (meal service, image processing, etc.)
└── utils/        # Utility functions
main.py           # FastAPI application entry point
pyproject.toml    # Python dependencies and project configuration
```

## User Preferences
- Prefers production-ready code with proper error handling
- Uses modern Python practices (async/await, pydantic settings)
- Follows FastAPI best practices
- Uses environment variables for configuration management

## Development Notes
- Server runs on port 5000 with host 0.0.0.0 for Replit compatibility
- Uses uv package manager for faster dependency management
- Includes comprehensive webhook testing capabilities
- Supports both WhatsApp Cloud API and Twilio for messaging flexibility