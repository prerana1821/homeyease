"""
FastAPI entry point for the WhatsApp Meal Planning Bot.
"""
import os
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from app.api.webhook import router as webhook_router
from app.config.settings import settings

app = FastAPI(
    title="Mambo - WhatsApp Meal Planning Bot",
    description="AI-powered meal planning bot with WhatsApp integration",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(webhook_router, prefix="/webhook", tags=["webhook"])

@app.get("/")
async def root():
    return {"message": "Mambo WhatsApp Meal Planning Bot is running!", "status": "healthy"}

@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "mambo-bot"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5000)