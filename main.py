"""
FastAPI entry point for the WhatsApp Meal Planning Bot.
Uses lifespan handlers and runs sync Supabase health checks in a threadpool
to avoid awaiting plain bools and the startup deprecation warning.
"""
import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.webhook import router as webhook_router
from app.api.twilio_webhook import router as twilio_webhook_router
from app.config.supabase import supabase_client  # global instance

logger = logging.getLogger("uvicorn.error")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 Starting Mambo Bot...")

    # Run the synchronous health_check in a threadpool to avoid awaiting a bool.
    try:
        loop = asyncio.get_running_loop()
        supabase_healthy = await loop.run_in_executor(
            None, supabase_client.health_check)
        if supabase_healthy:
            logger.info("✅ Supabase connection established")
        else:
            logger.warning("⚠️ Supabase connection failed")
    except Exception as exc:
        logger.exception("❌ Error initializing Supabase: %s", exc)

    # yield control to FastAPI (app is up)
    yield

    # Shutdown tasks (if any) go here
    logger.info("Shutting down Mambo Bot...")


app = FastAPI(
    title="Mambo - WhatsApp Meal Planning Bot",
    description="AI-powered meal planning bot with WhatsApp integration",
    version="1.0.0",
    lifespan=lifespan,
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
app.include_router(twilio_webhook_router, prefix="/webhook/twilio", tags=["twilio"])


@app.get("/")
async def root():
    return {
        "message": "Mambo WhatsApp Meal Planning Bot is running!",
        "status": "healthy"
    }


@app.get("/health")
async def health_check():
    """
    Async endpoint that uses run_in_executor to call the sync health_check.
    This avoids awaiting a plain bool and keeps the event loop responsive.
    """
    loop = asyncio.get_running_loop()
    db_ok = await loop.run_in_executor(None, supabase_client.health_check)
    return {
        "status": "healthy" if db_ok else "degraded",
        "service": "mambo-bot",
        "database": "connected" if db_ok else "disconnected",
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5000)
