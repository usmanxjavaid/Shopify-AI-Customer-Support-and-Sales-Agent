"""
core/tool_schemas.py
---------------------
Tool definitions in OpenAI-compatible function-calling format.

Both OpenRouter and Groq follow the OpenAI function-calling schema,
so these definitions work unchanged for either provider.

This is the "menu" we hand to the LLM — it uses these descriptions
and parameter definitions to decide which tool to call and what
arguments to pass.

Each schema must exactly match the actual function signature in
tools/shopify_tools.py — if they drift apart, tool calls will fail.
"""

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "search_knowledge_base",
            "description": (
                "Search the store's policy documents for answers about "
                "shipping times, return windows, warranty coverage, "
                "payment methods, sizing guides, or general FAQ. Use "
                "this for any policy question not answerable via order "
                "or product lookup tools."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {
                        "type": "string",
                        "description": "The customer's question, in their own words.",
                    }
                },
                "required": ["question"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_order_status",
            "description": (
                "Look up the current status of a customer's order "
                "by their order number. Use this when a customer asks "
                "about order status, shipping, or delivery."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "order_number": {
                        "type": "string",
                        "description": (
                            "The order number provided by the customer, "
                            "e.g. '1001' or '#1001'."
                        ),
                    }
                },
                "required": ["order_number"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_all_products",
            "description": (
                "Get the full list of products available in the store, "
                "with their IDs, titles, and availability. ALWAYS call "
                "this first before answering any product question, so "
                "you can identify the exact product the customer means."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_product_details",
            "description": (
                "Get detailed pricing, variants, and stock information "
                "for a specific product. Only call this AFTER using "
                "get_all_products to find the correct product ID."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "product_id": {
                        "type": "integer",
                        "description": (
                            "The exact Shopify product ID, obtained "
                            "from get_all_products. Never guess this."
                        ),
                    }
                },
                "required": ["product_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "verify_customer_email",
            "description": (
                "Verify that a customer's email matches the order "
                "they're asking about. ALWAYS call this and get "
                "'VERIFIED' before calling initiate_refund. If the "
                "customer hasn't given their email yet, ask for it first."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "order_number": {
                        "type": "string",
                        "description": "The order number to verify, e.g. '1001'.",
                    },
                    "email": {
                        "type": "string",
                        "description": "The email address the customer provided.",
                    },
                },
                "required": ["order_number", "email"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "initiate_refund",
            "description": (
                "Attempt to process a refund for an order. REQUIRES "
                "identity verification first via verify_customer_email. "
                "Automatically checks refund eligibility against store "
                "policy. If not eligible, returns REFUND_NOT_ELIGIBLE "
                "and you must escalate to a human next."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "order_number": {
                        "type": "string",
                        "description": "The order number to refund, e.g. '1001'.",
                    },
                    "reason": {
                        "type": "string",
                        "description": "The customer's stated reason for the refund.",
                    },
                    "verified_email": {
                        "type": "string",
                        "description": (
                            "The email that was confirmed VERIFIED via "
                            "verify_customer_email. Required."
                        ),
                    },
                },
                "required": ["order_number", "reason", "verified_email"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "escalate_to_human",
            "description": (
                "Hand off the conversation to a human support agent. "
                "Use this for frustrated customers, ineligible refunds, "
                "explicit requests for a human, or anything outside "
                "your capabilities."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "reason": {
                        "type": "string",
                        "description": (
                            "Clear explanation of why escalation is needed, "
                            "for the human agent's context."
                        ),
                    }
                },
                "required": ["reason"],
            },
        },
    },
]