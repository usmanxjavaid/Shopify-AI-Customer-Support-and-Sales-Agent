# 🛍️ Shopify AI Customer Support & Sales Agent

A production-grade AI customer support agent for Shopify stores — combining real-time order lookup, refund processing with policy guardrails, identity verification, and multi-channel support across Telegram and an embeddable web widget, built with FastAPI, OpenRouter, Groq, Shopify Admin API, and full audit logging.

![Python](https://img.shields.io/badge/python-3.11-blue) ![FastAPI](https://img.shields.io/badge/FastAPI-async-teal) ![License](https://img.shields.io/badge/license-MIT-green)

## ✨ Features

- 💬 **Multi-channel** — Telegram bot and embeddable web widget, one shared agent core
- 🧠 **Tool-calling agent** — LLM decides when to look up orders, check products, or process refunds, not scripted flows
- 📦 **Real-time order status** — live lookups against the Shopify Admin API
- 🛒 **Smart product Q&A** — LLM matches customer language against the live catalog, no hardcoded keyword search
- 💸 **Guarded refund processing** — auto-approved only within configurable policy (order age, amount, fulfillment status) — enforced in code, never left to LLM judgment
- 🔐 **Identity verification** — customers must verify their email against the order before any refund proceeds
- 🙋 **Human escalation** — automatic handoff with real-time Telegram notification to the store owner
- 🌍 **Multi-language** — automatically replies in whatever language the customer uses
- 🎙️ **Voice support (Telegram)** — speech-to-text and text-to-speech, customers can talk instead of type
- 💾 **Persistent memory** — Upstash Redis conversation history, with automatic in-memory fallback
- 🐘 **Full audit trail** — every tool call and escalation logged permanently to Neon PostgreSQL
- 🔁 **LLM fallback** — primary model via OpenRouter, automatic fallback to Groq on failure
- ✅ **CI/CD** — GitHub Actions runs the test suite on every push

## 📁 Project Structure
├── adapters/
│   ├── telegram_adapter.py     → Telegram bot (text + voice)
│   └── web_adapter.py          → FastAPI endpoint for the web widget
├── core/
│   ├── orchestrator.py         → tool-calling agent loop (LLM <-> tools)
│   ├── guardrails.py           → refund eligibility rules (pure logic)
│   ├── memory.py               → Redis-backed conversation history
│   ├── prompts.py              → system prompt
│   ├── tool_schemas.py         → tool definitions for the LLM
│   └── models.py               → shared data shapes
├── tools/
│   └── shopify_tools.py        → get_order_status, initiate_refund, verify_customer_email, etc.
├── integrations/
│   └── shopify_client.py       → Shopify Admin API wrapper
├── persistence/
│   ├── db.py                   → PostgreSQL table definitions
│   └── audit_log.py            → audit logging functions
├── tests/
│   └── test_guardrails.py      → automated pytest suite
├── config.py
├── logger.py
├── main.py                     → FastAPI entry point
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
└── .github/workflows/ci.yml

## ⚙️ Setup & Installation

### 1. Clone and install

```bash
git clone https://github.com/usmanxjavaid/Shopify-AI-Customer-Support-and-Sales-Agent
cd Shopify-AI-Customer-Support-and-Sales-Agent
python -m venv venv
venv\Scripts\activate      # Windows
source venv/bin/activate   # macOS/Linux
pip install -r requirements.txt
```

### 2. Create `.env`

```env
# Shopify
SHOPIFY_STORE_DOMAIN=
SHOPIFY_CLIENT_ID=
SHOPIFY_CLIENT_SECRET=
SHOPIFY_API_VERSION=2024-10

# LLM (primary + fallback)
OPENROUTER_API_KEY=
OPENROUTER_MODEL=deepseek/deepseek-chat
GROQ_API_KEY=
GROQ_MODEL=llama-3.3-70b-versatile

# Telegram
TELEGRAM_BOT_TOKEN=
OWNER_TELEGRAM_CHAT_ID=

# Voice (TTS)
GOOGLE_AI_API_KEY=

# Redis (Upstash) — conversation memory
UPSTASH_REDIS_REST_URL=
UPSTASH_REDIS_REST_TOKEN=

# PostgreSQL (Neon) — audit logging
DATABASE_URL=

# Business rules
REFUND_MAX_DAYS=30
REFUND_MAX_AMOUNT=100
```

### 3. Run the Telegram bot

```bash
python -m adapters.telegram_adapter
```

### 4. Run the web server (separate terminal)

```bash
uvicorn main:app --reload
```

### 5. Test the web widget

Open `widget_test.html` in a browser, or embed the widget snippet (see `/adapters/web_adapter.py` for the API contract) into a Shopify theme's `theme.liquid`, right before `</body>`.

## 🔄 Conversation Flow
Customer message (text or voice, any channel)
↓
Orchestrator sends message + history + tools to LLM
↓
LLM decides: reply directly, or call a tool
↓
get_order_status / get_all_products / get_product_details
verify_customer_email → initiate_refund (guardrails checked in code)
escalate_to_human → owner notified on Telegram
↓
Every tool call logged to PostgreSQL for audit
↓
Reply sent back through the original channel (text or voice)

## 🏗️ Tech Stack

| Layer | Technology |
|---|---|
| Language | Python 3.11 |
| Web framework | FastAPI (async) |
| Agent LLM (primary) | OpenRouter — DeepSeek |
| Agent LLM (fallback) | Groq — Llama 3.3 |
| Voice-to-text | Groq Whisper |
| Text-to-speech | Google AI Studio (Gemini TTS) |
| E-commerce | Shopify Admin API |
| Memory | Upstash Redis |
| Database | Neon PostgreSQL |
| Messaging | python-telegram-bot |
| Testing | pytest |
| CI/CD | GitHub Actions |
| Containerization | Docker + docker-compose |

## 🛡️ Guardrails

Refunds are **never** approved by LLM judgment alone. Every refund request passes through code-enforced rules before anything happens:

- Order must be `paid` and `fulfilled`
- Must be within `REFUND_MAX_DAYS` of fulfillment
- Must be under `REFUND_MAX_AMOUNT`
- Customer email must match the order's email on file

If any check fails, the agent automatically escalates to a human instead of proceeding.

## 📦 Per-Client Customization

To deploy for a new store, update `.env`:

```env
SHOPIFY_STORE_DOMAIN=client-store.myshopify.com
SHOPIFY_CLIENT_ID=<client's custom app credentials>
REFUND_MAX_DAYS=<client's return policy window>
REFUND_MAX_AMOUNT=<client's auto-approve limit>
```

Store policy documents (shipping, returns, warranty) can be customized in `core/prompts.py`.

## 🧪 Testing

```bash
pytest tests/ -v
```

Runs automatically on every push via `.github/workflows/ci.yml`.

## 🐳 Docker

```bash
docker-compose up --build
```

Runs both the Telegram bot and web server as separate containers from one image.

## ⚠️ Known Limitations

- Identity verification is email-based (matched against Shopify order data), not full account authentication — appropriate for guest-checkout stores, which make up the majority of Shopify orders
- Single-store per deployment — multi-tenant support (one deployment serving multiple stores) not yet implemented

## 📄 License

MIT License

## 👨‍💻 Author

Usman Javaid — [@usmanxjavaid](https://github.com/usmanxjavaid)