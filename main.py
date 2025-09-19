# main.py (improved)
"""
FastAPI entry point for the WhatsApp Meal Planning Bot (Twilio-only).
Improved startup/readiness behavior, structured logging, request-id middleware,
and graceful shutdown for Supabase client (if it supports close/shutdown).
"""
import asyncio
import logging
import os
import uuid
from contextlib import asynccontextmanager
from typing import Any, Dict, Optional

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.twilio_webhook import router as twilio_webhook_router
from app.config.supabase import supabase_client  # global instance; assumed to be sync client with health_check()

logger = logging.getLogger("uvicorn.error")

# config
HEALTH_CHECK_TIMEOUT = float(os.getenv("HEALTH_CHECK_TIMEOUT", "5.0"))
FAIL_ON_DB_STARTUP = os.getenv("FAIL_ON_DB_STARTUP", "false").lower() in ("1", "true", "yes")


async def _run_sync_in_executor(fn, *args, timeout: float = HEALTH_CHECK_TIMEOUT):
    """
    Helper to run blocking sync functions in the default threadpool with a timeout.
    Returns the function's result or raises TimeoutError.
    """
    loop = asyncio.get_running_loop()
    return await asyncio.wait_for(loop.run_in_executor(None, fn, *args), timeout=timeout)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 Starting Mambo Bot...")

    # Basic startup: check Supabase health (sync) in executor to avoid awaiting plain bool.
    supabase_healthy = False
    try:
        try:
            supabase_healthy = await _run_sync_in_executor(supabase_client.health_check)
        except asyncio.TimeoutError:
            logger.warning("⚠️ Supabase health_check timed out after %.1fs", HEALTH_CHECK_TIMEOUT)
            supabase_healthy = False
        except Exception as exc:
            logger.exception("❌ Unexpected error calling supabase_client.health_check: %s", exc)
            supabase_healthy = False

        app.state.supabase_healthy = bool(supabase_healthy)
        logger.info("Supabase health: %s", app.state.supabase_healthy)

        if not app.state.supabase_healthy and FAIL_ON_DB_STARTUP:
            # If fail-fast is enabled, raise to prevent server start.
            logger.error("FAIL_ON_DB_STARTUP enabled and Supabase unhealthy. Aborting startup.")
            raise RuntimeError("Supabase unhealthy on startup")

        # any other startup tasks like scheduling background tasks can be started here
    except Exception:
        # bubble up so uvicorn doesn't silently succeed when critical init fails
        logger.exception("Critical startup error")
        raise

    # yield control to FastAPI (app is up)
    try:
        yield
    finally:
        # Shutdown cleanup
        logger.info("Shutting down Mambo Bot...")
        # Attempt graceful shutdown of supabase_client if it has a close/shutdown
        try:
            close_fn = getattr(supabase_client, "close", None) or getattr(supabase_client, "shutdown", None)
            if callable(close_fn):
                # run in executor in case it's blocking
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, close_fn)
                logger.info("Supabase client closed gracefully")
        except Exception:
            logger.exception("Error while closing supabase client during shutdown")


app = FastAPI(
    title="Mambo - WhatsApp Meal Planning Bot",
    description="AI-powered meal planning bot with Twilio WhatsApp integration",
    version="1.0.0",
    lifespan=lifespan,
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # you can lock this down in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Simple request-id middleware + structured request logging
@app.middleware("http")
async def add_request_id_and_log(request: Request, call_next):
    request_id = request.headers.get("X-Request-Id") or str(uuid.uuid4())
    # attach to state for handlers to use
    request.state.request_id = request_id
    logger.info("→ Incoming request %s %s id=%s from=%s", request.method, request.url.path, request_id, request.client)
    try:
        response: Response = await call_next(request)
    except Exception as exc:
        logger.exception("Handler error for request id=%s: %s", request_id, exc)
        # consistent JSON error
        return JSONResponse({"ok": False, "status": 500, "message": "Internal server error", "diagnostics": {"error": str(exc)}}, status_code=500)
    logger.info("← Completed request id=%s status=%s", request_id, getattr(response, "status_code", None))
    # set request id on response headers for tracing
    response.headers["X-Request-Id"] = request_id
    return response

# Include routers - Twilio-only
app.include_router(twilio_webhook_router, prefix="/webhook", tags=["webhook"])

@app.get("/")
async def root() -> Dict[str, str]:
    return {"message": "Mambo WhatsApp Meal Planning Bot is running!", "status": "healthy"}

@app.head("/api")
async def api_head():
    # HEAD should return headers only; FastAPI will return status without a JSON body
    return Response(status_code=200)

@app.get("/health")
async def health_check():
    """
    Liveness style check — is the process up? We run a quick supabase health_check here (with timeout)
    but don't fail hard; return degraded if DB is down.
    """
    try:
        try:
            db_ok = await _run_sync_in_executor(supabase_client.health_check)
        except asyncio.TimeoutError:
            logger.warning("⚠️ Supabase health_check timed out on /health")
            db_ok = False
        except Exception as exc:
            logger.exception("Error invoking supabase health on /health: %s", exc)
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
        logger.exception("Error during /health: %s", exc)
        return JSONResponse({"status": "error", "service": "mambo-bot", "error": str(exc)}, status_code=500)

@app.get("/ready")
async def readiness_check():
    """
    Readiness: is the app ready to accept traffic? Uses cached state from startup when available.
    If state was never set, we attempt one-shot check (bounded).
    """
    supabase_state: Optional[bool] = getattr(app.state, "supabase_healthy", None)
    if supabase_state is None:
        # fallback: run quick check but don't block too long
        try:
            supabase_state = await _run_sync_in_executor(supabase_client.health_check, timeout=2.0)
        except Exception:
            supabase_state = False

    if supabase_state:
        return JSONResponse({"ready": True, "database": "connected"}, status_code=200)
    return JSONResponse({"ready": False, "database": "disconnected"}, status_code=503)


if __name__ == "__main__":
    import uvicorn
    # Allow overriding host/port via env vars, keep dev-friendly defaults
    uvicorn.run("main:app", host=os.getenv("HOST", "0.0.0.0"), port=int(os.getenv("PORT", 5000)), reload=True)
