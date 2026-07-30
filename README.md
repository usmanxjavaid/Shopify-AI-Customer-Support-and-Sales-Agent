# 🛍️ Shopify AI Customer Support & Sales Agent

A production-grade AI customer support agent for Shopify stores — combining real-time order lookup, shipment-aware refund processing, identity verification, a policy/FAQ knowledge base, and a full email-based ticketing system, across Telegram and an embeddable web widget. Built with FastAPI, OpenRouter, Groq, Shopify Admin API, ChromaDB, Resend, and full audit logging.

![Python](https://img.shields.io/badge/python-3.11-blue) ![FastAPI](https://img.shields.io/badge/FastAPI-async-teal) ![License](https://img.shields.io/badge/license-MIT-green)

## ✨ Features

- 💬 **Multi-channel** — Telegram bot (text + voice) and embeddable web widget, one shared agent core
- 🧠 **Tool-calling agent** — LLM decides when to look up orders, check products, search policy docs, or process refunds
- 📦 **Real-time order status** — live lookups against the Shopify Admin API
- 🛒 **Smart product Q&A** — LLM matches customer language against the live catalog, no hardcoded keyword search
- 📚 **Knowledge base (RAG)** — answers shipping, returns, warranty, and FAQ questions from real store policy documents (PDF/DOCX/TXT)
- 💸 **Shipment-aware refund logic** — unshipped orders refund automatically; fulfilled orders require a physical return confirmed by a human before any money moves — never guesses, never trusts a customer's word alone
- 🔐 **Identity verification** — customers must verify their email against the order before any refund proceeds
- 🎫 **Full ticketing system** — escalations become real tickets with threaded conversations; once escalated, the AI steps back and a human takes over until resolved
- 📧 **Two-way email support** — store owner gets emailed on escalation and can reply directly, either from their inbox or the admin dashboard; replies route back to the customer on their original channel
- 🙋 **Real-time Telegram alerts** — instant owner notification alongside email
- 🌍 **Multi-language** — automatically replies in whatever language the customer uses
- 🎙️ **Voice support** — speech-to-text and text-to-speech on both Telegram (native voice bubbles) and the web widget (custom waveform player)
- 💾 **Persistent memory** — Upstash Redis conversation history, with automatic in-memory fallback
- 🐘 **Full audit trail** — every tool call and ticket logged permanently to Neon PostgreSQL
- 🖥️ **Admin dashboard** — password-protected, with stats, a full ticket inbox, threaded replies, and activity log
- 🔁 **LLM fallback** — primary model via OpenRouter, automatic fallback to Groq on failure
- ✅ **CI/CD** — GitHub Actions runs the test suite on every push

## 📁 Project Structure

```
adapters/
    telegram_adapter.py    - Telegram bot (text + native voice bubbles)
    web_adapter.py          - FastAPI endpoints for the web widget (text + voice)
    admin_routes.py           - password-protected admin dashboard + ticket inbox
    email_webhook.py            - receives inbound email replies, routes to customers

core/
    orchestrator.py         - tool-calling agent loop; steps back once a ticket is open
    guardrails.py             - shipment-aware refund path logic (pure logic, testable)
    memory.py                   - Redis-backed conversation history
    prompts.py                    - system prompt
    tool_schemas.py                 - tool definitions for the LLM
    models.py                         - shared data shapes

tools/
    shopify_tools.py        - get_order_status, initiate_refund, verify_customer_email, escalate_to_human
    knowledge_tools.py         - search_knowledge_base

integrations/
    shopify_client.py       - Shopify Admin API wrapper (orders, products, fulfillment orders, refunds)
    voice_service.py           - shared speech-to-text / text-to-speech (Groq Whisper, Gemini TTS)

knowledge_base/
    document_readers.py     - PDF/DOCX/TXT to raw text
    chunker.py                 - raw text to overlapping chunks
    vector_store.py               - chunks to ChromaDB (add/query/clear)
    indexer.py                       - orchestrates the full indexing pipeline

knowledge/                  - store policy documents live here (PDF/DOCX/TXT)

persistence/
    db.py                    - PostgreSQL table definitions (tickets, messages, tool_calls)
    audit_log.py                - tool call logging (write)
    queries.py                     - dashboard + ticket queries (read/write)

tests/
    test_guardrails.py      - automated pytest suite for refund path logic

config.py
logger.py
main.py                     - FastAPI entry point
build_index.py                - rebuild the knowledge base index
requirements.txt
Dockerfile
docker-compose.yml

.github/
    workflows/
        ci.yml               - GitHub Actions test runner
```

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

# Admin dashboard
ADMIN_PASSWORD=

# Email (Resend) — ticket notifications and two-way replies
RESEND_API_KEY=
OWNER_EMAIL=
RESEND_INBOUND_ADDRESS=

# Business rules
REFUND_MAX_DAYS=30
REFUND_MAX_AMOUNT=100
```

### 3. Add store policy documents

Drop PDF, DOCX, or TXT files (shipping policy, return policy, FAQ, terms of service) into `knowledge/`, then build the index:

```bash
python build_index.py
```

Re-run this any time documents in `knowledge/` change.

### 4. Run the Telegram bot

```bash
python -m adapters.telegram_adapter
```

### 5. Run the web server (separate terminal)

```bash
uvicorn main:app --reload
```

### 6. Access the admin dashboard

Visit `http://127.0.0.1:8000/admin`, log in with `ADMIN_PASSWORD`. From here you can view stats, open any ticket to see the full conversation thread, reply directly, and mark tickets resolved.

### 7. Embed the web widget

Copy the widget snippet into a Shopify theme's `theme.liquid`, right before `</body>`, and set `VELVORA_API_BASE` to your server's public URL.

### 8. Set up two-way email (optional but recommended)

1. Create a free [Resend](https://resend.com) account
2. Under Receiving Emails, grab your free inbound address and set it as `RESEND_INBOUND_ADDRESS`
3. Add a webhook pointing to `https://your-domain/webhooks/resend/inbound`
4. Replying to any ticket notification email now routes straight back to the customer

## 🔄 Conversation Flow

```
1. Customer sends a message (text or voice, any channel)

2. If a ticket is already open for this customer, the AI steps back
   and routes the message straight into the ticket thread instead
   of responding itself -- a human is already handling it

3. Otherwise, the orchestrator sends message + history + tool list
   to the LLM

4. LLM decides: reply directly, or call a tool
   - get_order_status       -> real-time order lookup
   - get_all_products        -> product catalog
   - get_product_details       -> pricing and stock for one product
   - search_knowledge_base       -> answers from real policy documents
   - verify_customer_email         -> required before any refund
   - initiate_refund                 -> unshipped orders refund
                                        automatically; fulfilled orders
                                        create a return ticket instead
   - escalate_to_human                 -> creates/updates a support
                                          ticket, notifies the owner
                                          via Telegram and email

5. Every tool call is logged to PostgreSQL for a full audit trail

6. The store owner can reply from the admin dashboard or directly
   from their email inbox -- either way, the reply reaches the
   customer on their original channel

7. Final reply is sent back through the original channel (text or voice)
```

## 🏗️ Tech Stack

| Layer | Technology |
|---|---|
| Language | Python 3.11 |
| Web framework | FastAPI (async) |
| Agent LLM (primary) | OpenRouter — DeepSeek |
| Agent LLM (fallback) | Groq — Llama 3.3 |
| Voice-to-text | Groq Whisper |
| Text-to-speech | Google AI Studio (Gemini TTS) |
| E-commerce | Shopify Admin API (Orders, Products, Fulfillment Orders) |
| Knowledge base | ChromaDB + Gemini Embeddings |
| Memory | Upstash Redis |
| Database | Neon PostgreSQL |
| Email | Resend (outbound + inbound webhook) |
| Messaging | python-telegram-bot |
| Testing | pytest |
| CI/CD | GitHub Actions |
| Containerization | Docker + docker-compose |
| Hosting | AWS |

## 🛡️ Guardrails

Refunds are **never** approved by LLM judgment alone. Every refund request passes through code-enforced rules:

- Order must be `paid`, and not already refunded
- Must be within `REFUND_MAX_DAYS` of fulfillment and under `REFUND_MAX_AMOUNT`
- Customer email must match the order's email on file
- **Unshipped orders** refund automatically — nothing physical to return
- **Fulfilled orders always require a physical return**, confirmed by a human via the admin dashboard, before a refund is issued — this matches Shopify's own real-world return workflow and avoids ever refunding an order the customer hasn't actually sent back

If any check fails, the agent automatically creates a support ticket instead of proceeding.

## 🎫 Ticketing

Once a conversation is escalated, it becomes a persistent ticket with a full message thread. The AI **stops responding** to that customer until a human resolves the ticket — matching how real helpdesks (Zendesk, Help Scout) behave. The store owner can respond two ways:

- **From the admin dashboard** — open the ticket, type a reply, it's delivered instantly (Telegram) or by email (web customers)
- **From their own inbox** — replying to the ticket notification email is automatically parsed and routed back to the customer

## 📦 Per-Client Customization

To deploy for a new store, update `.env`:

```env
SHOPIFY_STORE_DOMAIN=client-store.myshopify.com
SHOPIFY_CLIENT_ID=<client's custom app credentials>
REFUND_MAX_DAYS=<client's return policy window>
REFUND_MAX_AMOUNT=<client's auto-approve limit>
```

Replace the documents in `knowledge/` with the client's own policies and re-run `python build_index.py`.

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
- Email reply parsing strips common quoted-reply markers but isn't perfect across every email client
- Single-store per deployment — multi-tenant support (one deployment serving multiple stores) not yet implemented

## 📄 License

MIT License

## 👨‍💻 Author

Usman Javaid — [@usmanxjavaid](https://github.com/usmanxjavaid)