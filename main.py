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

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from adapters.web_adapter import router as web_router
from persistence.db import init_db
from logger import get_logger

logger = get_logger(__name__)

app = FastAPI(title="Velvora AI Support Agent")

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


@app.on_event("startup")
def on_startup():
    """Ensures database tables exist before accepting any requests."""
    init_db()
    logger.info("FastAPI app started, database ready")


@app.get("/health")
async def health():
    """Simple health check endpoint."""
    return {"status": "ok"}