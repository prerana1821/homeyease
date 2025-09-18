# Homeyease

No fluff. This repo runs a WhatsApp-based meal-planning assistant that:

* Accepts messages & images via WhatsApp Cloud API
* Uses Supabase as the backend (auth + Postgres)
* Uses Google Cloud Vision for ingredient detection
* Responds with personalized meal suggestions, recipes, and weekly plans

Think: friendly meal coach on WhatsApp. Production-ready-ish, but don’t be sloppy with secrets.

---

# Quick status

* ✅ Webhook endpoints (verify + message receive)
* ✅ Supabase singleton client with health checks
* ✅ Image processing via Google Vision integration
* ✅ Onboarding flows, intent classification, meal recommendation logic
* ✅ Local test + ngrok E2E instructions included below

---

# Contents

* `main.py` — FastAPI entrypoint (lifespan-based startup)
* `app/api/webhook.py` — WhatsApp webhook verify + message handler route
* `app/config/settings.py` — pydantic Settings (`.env` support)
* `app/config/supabase.py` — Supabase singleton client
* `app/services/message_handler.py` — message processing & routing
* `tests/` — pytest tests (webhook + handler unit tests)
* other modules: vision integration, meal recommender, DB mappers

---

# Prerequisites

* Python 3.10+ (venv recommended)
* Supabase project (Project URL + Service Role Key)
* Meta (Facebook) Developer App + WhatsApp Cloud API access (Phone Number ID + token)
* Google Cloud service account JSON for Vision API (optional for image flows)
* (Optional) Twilio account if you use Twilio fallback channels

---

# .env (create at repo root — DO NOT COMMIT)

Create `.env` and fill values. Example `env.example`:

```
# Supabase (server-side only)
SUPABASE_URL=https://<project-ref>.supabase.co
SUPABASE_SERVICE_ROLE_KEY=eyJhbGciOiJI...service_role...

# Optional direct Postgres URI if used for other tooling
DATABASE_URL=postgresql://postgres:password@db.<project-ref>.supabase.co:5432/postgres

# WhatsApp
WHATSAPP_TOKEN=EAAB...long_token_here...
WHATSAPP_VERIFY_TOKEN=P9WuIqKcQ0LtFC30t6PnPZ...  # choose a long random token
WHATSAPP_PHONE_NUMBER_ID=1234567890

# OpenAI (if used)
OPENAI_API_KEY=sk-...

# Google Vision (path to JSON credentials file)
GOOGLE_APPLICATION_CREDENTIALS=/path/to/gcloud-key.json

# Twilio (optional)
TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxx
TWILIO_AUTH_TOKEN=your_twilio_auth_token
TWILIO_PHONE_NUMBER="+12727882550"
```

Rules: never commit `.env`. Use secret managers for CI/deploy.

---

# Local setup (fast)

```bash
# clone
git clone <repo>
cd <repo>

# python env
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# populate .env (see example above)
# run
uvicorn main:app --reload --port 5000
```

Open `http://127.0.0.1:5000/` — should return a simple status JSON.

---

# Quick manual tests

1. Health check

```bash
curl -s http://127.0.0.1:5000/health | jq .
```

2. Webhook verification (what Meta will call)

```bash
curl -v "http://127.0.0.1:5000/webhook/whatsapp?hub.mode=subscribe&hub.verify_token=<WHATSAPP_VERIFY_TOKEN>&hub.challenge=12345"
# expected response body: 12345
```

3. Simulate incoming message (POST)

```bash
curl -X POST http://127.0.0.1:5000/webhook/whatsapp \
  -H "Content-Type: application/json" \
  -d '<sample_whatsapp_payload.json>'
# expected: {"status":"ok"} and logs show handler processing
```

4. Expose locally and test with Meta:

```bash
# start ngrok
ngrok http 5000
# copy https://abcd.ngrok.io and register webhook in Meta dashboard:
# Callback URL: https://abcd.ngrok.io/webhook/whatsapp
# Verify Token: <WHATSAPP_VERIFY_TOKEN>
```

Once verified, use Graph API to send a test message (requires WHATSAPP\_TOKEN + PHONE\_NUMBER\_ID).

---

# Running tests

```bash
pip install -r dev-requirements.txt   # includes pytest, httpx, pytest-asyncio
pytest -q
```

Notes:

* If `MessageHandler.process_webhook` is async, tests use `AsyncMock`.
* Unit tests mock external services (Supabase, Vision) for determinism.

---

# Deployment notes (ruthless)

* Use `SUPABASE_SERVICE_ROLE_KEY` **only** on trusted backend servers. Never expose it in frontend code. Prefer ANON with RLS for client flows.
* Store secrets in hosting platform secret manager (Render, Heroku, Vercel, AWS Secrets Manager, GitHub Actions Secrets).
* Run migrations / initialize Supabase tables ahead of app startup.
* Use logging (not prints) — the project uses `uvicorn` logger by default.
* Add rate limiting & retries for external calls (WhatsApp / Supabase / Vision) in production.

---

# Security & compliance (do not skip)

* Rotate keys regularly. Revoke compromised tokens immediately.
* Enable Supabase Row Level Security (RLS) and least-privilege roles for production.
* Don’t log tokens or PII (redact phone numbers in logs).
* For WhatsApp: obtain proper business verification for production (Meta requirements).

---

# Troubleshooting quick hits

* `Invalid Supabase URL format` → you set `DATABASE_URL` into `SUPABASE_URL`. `SUPABASE_URL` must be `https://<ref>.supabase.co`.
* `object bool can't be used in 'await' expression` → you awaited a sync health\_check(); use `await loop.run_in_executor(None, supabase_client.health_check)` or `health_check_async()`.
* 403 on webhook verify → confirm `WHATSAPP_VERIFY_TOKEN` matches between .env and Meta dashboard.
* 401/403 on Graph API calls → token expired or wrong token (use system-user token for prod).

---

# Helpful snippets

**FastAPI webhook verify snippet**

```py
from fastapi import APIRouter, Request, HTTPException, Query
from fastapi.responses import PlainTextResponse
from app.config.settings import settings

router = APIRouter()

@router.get("/whatsapp")
async def verify_webhook(hub_mode: str = Query(alias="hub.mode"),
                         hub_challenge: str = Query(alias="hub.challenge"),
                         hub_verify_token: str = Query(alias="hub.verify_token")):
    if hub_mode == "subscribe" and hub_verify_token == settings.whatsapp_verify_token:
        return PlainTextResponse(hub_challenge)
    raise HTTPException(status_code=403, detail="Invalid verification token")
```

**Send message via Graph API**

```bash
curl -X POST "https://graph.facebook.com/v18.0/<PHONE_NUMBER_ID>/messages" \
  -H "Authorization: Bearer $WHATSAPP_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "messaging_product":"whatsapp",
    "to":"<E164_RECIPIENT>",
    "type":"text",
    "text":{"body":"Hello from Mambo Bot"}
  }'
```

---
