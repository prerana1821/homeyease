"""
FastAPI entry point for the WhatsApp Meal Planning Bot (Twilio-only).
Uses lifespan handlers and runs sync Supabase health checks in a threadpool
to avoid awaiting plain bools and the startup deprecation warning.
"""
import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Any, Dict

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse, JSONResponse

from app.api.twilio_webhook import router as twilio_webhook_router
from app.config.supabase import supabase_client  # global instance

logger = logging.getLogger("uvicorn.error")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 Starting Mambo Bot...")

    # Run the synchronous health_check in a threadpool to avoid awaiting a bool.
    try:
        loop = asyncio.get_running_loop()
        # Put a short timeout on the health-check so startup won't hang indefinitely.
        try:
            supabase_healthy = await asyncio.wait_for(
                loop.run_in_executor(None, supabase_client.health_check),
                timeout=5.0,
            )
        except asyncio.TimeoutError:
            supabase_healthy = False
            logger.warning("⚠️ Supabase health_check timed out")

        if supabase_healthy:
            logger.info("✅ Supabase connection established")
        else:
            logger.warning("⚠️ Supabase connection failed or is unhealthy")
    except Exception as exc:
        logger.exception("❌ Error initializing Supabase: %s", exc)

    # yield control to FastAPI (app is up)
    yield

    # Shutdown tasks (if any) go here
    logger.info("Shutting down Mambo Bot...")


app = FastAPI(
    title="Mambo - WhatsApp Meal Planning Bot",
    description="AI-powered meal planning bot with Twilio WhatsApp integration",
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

# Include routers - Twilio-only
# Routes in app/api/twilio_webhook.py are exposed at:
#  - POST /webhook/whatsapp  (Twilio form-encoded webhook)
#  - GET  /webhook/test      (diagnostics)
app.include_router(twilio_webhook_router, prefix="/webhook", tags=["webhook"])


@app.get("/")
async def root() -> Dict[str, str]:
    return {
        "message": "Mambo WhatsApp Meal Planning Bot is running!",
        "status": "healthy",
    }


@app.head("/api")
async def api_head():
    # HEAD should return headers only; FastAPI will not return a body here.
    return PlainTextResponse(status_code=200, content="")


@app.get("/health")
async def health_check():
    """
    Async endpoint that uses run_in_executor to call the sync health_check.
    This avoids awaiting a plain bool and keeps the event loop responsive.
    """
    try:
        loop = asyncio.get_running_loop()
        # Same timeout logic as startup; protects the endpoint from hanging.
        try:
            db_ok = await asyncio.wait_for(
                loop.run_in_executor(None, supabase_client.health_check),
                timeout=5.0,
            )
        except asyncio.TimeoutError:
            logger.warning("⚠️ Supabase health_check timed out on /health")
            db_ok = False

        return JSONResponse(
            {
                "status": "healthy" if db_ok else "degraded",
                "service": "mambo-bot",
                "database": "connected" if db_ok else "disconnected",
            },
            status_code=200 if db_ok else 503,
        )
    except Exception as exc:
        logger.exception("Error during /health check: %s", exc)
        return JSONResponse(
            {
                "status": "error",
                "service": "mambo-bot",
                "database": "unknown",
                "error": str(exc),
            },
            status_code=500,
        )


if __name__ == "__main__":
    # Note: for local dev you can run:
    # uvicorn main:app --host 0.0.0.0 --port 5000 --reload
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=5000)
