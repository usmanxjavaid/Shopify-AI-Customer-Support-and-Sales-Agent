"""
main.py
-------
FastAPI application entry point for HTTP-based channels
(web widget now, WhatsApp webhook later).

Run with:
    uvicorn main:app --reload

Telegram runs separately via:
    python -m adapters.telegram_adapter

These are two independent processes since Telegram uses polling
(no HTTP server needed) while web/WhatsApp need an actual server
listening for requests.
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from adapters.telegram_adapter import router as telegram_router, _telegram_app
from adapters.admin_routes import router as admin_router
from adapters.web_adapter import router as web_router
from adapters.email_webhook import router as email_webhook_router
from adapters.whatsapp_adapter import router as whatsapp_router
from persistence.db import init_db
from logger import get_logger

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Modern replacement for the deprecated @app.on_event("startup").

    Code before `yield` runs once on startup (ensures DB tables exist).
    Code after `yield` would run on shutdown (nothing needed there yet).
    """
    init_db()
    await _telegram_app.initialize()

    logger.info("FastAPI app started, database ready")

    yield

    await _telegram_app.shutdown()
    logger.info("FastAPI app shutting down")


app = FastAPI(title="Velvora AI Support Agent", lifespan=lifespan)

# Allow the widget to be embedded on any storefront domain.
# In real production, restrict this to your actual store's domain
# instead of "*" for better security.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(web_router)
app.include_router(admin_router)
app.include_router(telegram_router)
app.include_router(email_webhook_router)
app.include_router(whatsapp_router)

@app.get("/health")
async def health():
    """Simple health check endpoint."""
    return {"status": "ok"}