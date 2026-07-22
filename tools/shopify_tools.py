"""
tools/shopify_tools.py
----------------------
LLM-callable tools for the Shopify e-commerce agent.

These are the ONLY functions the LLM is allowed to call.
Each tool has a clear docstring because we use those descriptions
to tell the LLM what each tool does and when to use it.

Design principle:
    LLM handles intent and fuzzy matching.
    Tools handle precise, structured data fetching and actions.

    Wrong: tool tries to search product by customer's raw text
    Right: LLM identifies product from catalog, tool fetches by ID

Flow:
    LLM decides to call a tool
        → we execute it here
        → guardrails check runs (for action tools)
        → result returned to LLM as plain text
        → LLM crafts final customer-facing reply
"""

from typing import Optional
from integrations.shopify_client import ShopifyClient
from core.guardrails import check_refund_eligibility
import requests as http_requests
from config import settings
from logger import get_logger

logger = get_logger(__name__)

# Single shared client instance
_client = ShopifyClient()


# ------------------------------------------------------------------
# Order tools
# ------------------------------------------------------------------

def get_order_status(order_number: str) -> str:
    """
    Fetches the current status of an order by its order number.

    Use this when the customer asks about their order status,
    shipping update, or wants to know what is happening with
    their purchase. Ask the customer for their order number
    if they haven't provided it yet.

    Args:
        order_number: The order number provided by the customer.
                      Can be "1001", "#1001" — we clean it up.

    Returns:
        Plain text summary of the order for the LLM to use
        in its reply to the customer.
    """
    cleaned = order_number.strip().lstrip("#").strip()
    logger.info(f"Fetching order status for order number: #{cleaned}")

    try:
        orders = _client.get_orders_by_number(cleaned)

        if not orders:
            logger.warning(f"No order found for number: #{cleaned}")
            return (
                f"No order found with number #{cleaned}. "
                f"Please ask the customer to double-check their "
                f"order number from their confirmation email."
            )

        order = orders[0]

        if order.fulfillment_status == "fulfilled":
            fulfillment_text = "shipped and on its way"
        elif order.fulfillment_status == "partial":
            fulfillment_text = "partially shipped"
        else:
            fulfillment_text = "being prepared for shipment"

        items_text = ", ".join(order.line_items)

        result = (
            f"Order {order.order_number}:\n"
            f"- Status: {order.status}\n"
            f"- Fulfillment: {fulfillment_text}\n"
            f"- Items: {items_text}\n"
            f"- Total: {order.currency} {order.total_price:.2f}\n"
            f"- Placed on: {order.created_at.strftime('%B %d, %Y')}"
        )

        logger.info(f"Order {order.order_number} fetched successfully")
        return result

    except Exception as e:
        logger.error(f"Error fetching order #{cleaned}: {e}")
        return (
            "I am having trouble fetching the order details right now. "
            "Please try again in a moment."
        )


# ------------------------------------------------------------------
# Product tools
# ------------------------------------------------------------------

def get_all_products() -> str:
    """
    Returns a list of all products available in the store.

    Use this FIRST when a customer asks about any product,
    price, or availability. Look at the returned product list
    and use your judgment to identify which product the customer
    is referring to. Then call get_product_details() with the
    exact product ID to get full pricing and stock information.

    Never guess a product ID — always get it from this list first.

    Returns:
        Plain text list of all products with their IDs and titles
        for the LLM to identify the correct product from.
    """
    logger.info("Fetching product catalog")

    try:
        products = _client.get_all_products()

        if not products:
            return "No products are currently available in the store."

        lines = ["Available products:"]
        for p in products:
            status = (
                "available" if p["status"] == "active"
                else "unavailable"
            )
            lines.append(
                f"- ID {p['id']}: {p['title']} ({status})"
            )

        result = "\n".join(lines)
        logger.info(f"Returned catalog of {len(products)} products")
        return result

    except Exception as e:
        logger.error(f"Error fetching product catalog: {e}")
        return (
            "I am having trouble fetching our product catalog. "
            "Please try again in a moment."
        )


def get_product_details(product_id: int) -> str:
    """
    Returns detailed information about a specific product by its ID.

    Use this AFTER calling get_all_products() and identifying
    which product ID matches what the customer is asking about.
    Never call this without first confirming the product ID
    from get_all_products().

    Args:
        product_id: Exact Shopify product ID from get_all_products().

    Returns:
        Plain text product details including variants,
        pricing, and stock levels.
    """
    logger.info(f"Fetching product details for ID: {product_id}")

    try:
        product = _client.get_product_by_id(product_id)

        if not product:
            return (
                f"Product with ID {product_id} could not be found."
            )

        variants_text = ""
        for v in product.get("variants", []):
            stock = v.get("inventory_quantity", 0)
            stock_text = "In stock" if stock > 0 else "Out of stock"
            variants_text += (
                f"\n  - {v['title']}: "
                f"${v['price']} ({stock_text})"
            )

        result = (
            f"Product: {product['title']}\n"
            f"Status: {product['status']}\n"
            f"Variants:{variants_text}"
        )

        logger.info(
            f"Product details fetched for ID: {product_id}"
        )
        return result

    except Exception as e:
        logger.error(f"Error fetching product {product_id}: {e}")
        return (
            "I am having trouble fetching product details. "
            "Please try again in a moment."
        )

def verify_customer_email(order_number: str, email: str) -> str:
    """
    Verifies that the given email matches the customer email on file
    for a specific order. Use this BEFORE processing a refund, to
    confirm the person chatting is actually the customer who placed
    the order.

    Args:
        order_number: The order number to verify against.
        email:        The email the customer provided in chat.

    Returns:
        "VERIFIED" if the email matches the order's customer email.
        "NOT_VERIFIED: <reason>" if it doesn't match or can't be checked.
    """
    cleaned_order = order_number.strip().lstrip("#").strip()
    cleaned_email = email.strip().lower()

    logger.info(
        f"Verifying email for order #{cleaned_order} | "
        f"provided email: {cleaned_email}"
    )

    try:
        orders = _client.get_orders_by_number(cleaned_order)

        if not orders:
            return f"NOT_VERIFIED: Order #{cleaned_order} not found."

        order = orders[0]

        if not order.customer_email:
            logger.warning(
                f"Order #{cleaned_order} has no email on file"
            )
            return (
                f"NOT_VERIFIED: Order #{cleaned_order} has no email on "
                f"file to verify against. Escalate to a human."
            )

        if order.customer_email.strip().lower() == cleaned_email:
            logger.info(f"Email verified for order #{cleaned_order}")
            return "VERIFIED"

        logger.warning(
            f"Email mismatch for order #{cleaned_order}: "
            f"provided '{cleaned_email}' vs "
            f"actual '{order.customer_email}'"
        )
        return (
            "NOT_VERIFIED: The email provided does not match our "
            "records for this order."
        )

    except Exception as e:
        logger.error(f"Error verifying email for #{cleaned_order}: {e}")
        return "NOT_VERIFIED: An error occurred during verification."

# ------------------------------------------------------------------
# Refund tools
# ------------------------------------------------------------------

def initiate_refund(
    order_number: str, reason: str, verified_email: str
) -> str:
    """
    Attempts to initiate a refund for an order.

    REQUIRES identity verification first. You must call
    verify_customer_email and receive "VERIFIED" before ever
    calling this tool. Pass the same email that was verified.

    Guardrails run automatically inside this tool. If the order
    does not meet refund policy requirements, the refund will NOT
    be issued and you will receive an instruction to escalate.
    Always follow that instruction — never try to override it.

    Args:
        order_number:   The order number to refund e.g. "1001".
        reason:         The customer's stated reason for the refund.
        verified_email: The email that was confirmed via
                        verify_customer_email. Required — do not
                        guess or skip this.

    Returns:
        Plain text result — either refund confirmation or
        an instruction to escalate with the reason why.
    """
    cleaned = order_number.strip().lstrip("#").strip()
    logger.info(
        f"Refund requested for order #{cleaned} | reason: {reason} | "
        f"claimed verified email: {verified_email}"
    )

    try:
        orders = _client.get_orders_by_number(cleaned)

        if not orders:
            return (
                f"Order #{cleaned} could not be found. "
                f"Please ask the customer to verify their order number."
            )

        order = orders[0]

        # Re-verify server-side — never trust the LLM's claim alone
        if (
            not order.customer_email
            or order.customer_email.strip().lower()
            != verified_email.strip().lower()
        ):
            logger.warning(
                f"Refund blocked — email verification failed for "
                f"order #{cleaned}"
            )
            return (
                "REFUND_NOT_ELIGIBLE: Identity could not be verified "
                "for this order. Please escalate to a human agent."
            )

        eligibility = check_refund_eligibility(
            order_total=order.total_price,
            order_fulfilled_at=order.created_at,
            fulfillment_status=order.fulfillment_status,
            financial_status=order.status,
        )

        if not eligibility.eligible:
            logger.info(
                f"Refund blocked for order {order.order_number}: "
                f"{eligibility.reason}"
            )
            return (
                f"REFUND_NOT_ELIGIBLE: {eligibility.reason} "
                f"Please escalate this to a human agent."
            )

        success = _client.create_refund(
            order_id=order.order_id,
            amount=order.total_price,
            reason=reason,
        )

        if success:
            logger.info(
                f"Refund issued for order {order.order_number}"
            )
            return (
                f"Refund successfully initiated for order "
                f"{order.order_number}. "
                f"{order.currency} {order.total_price:.2f} will be "
                f"returned to the original payment method "
                f"within 5-7 business days."
            )
        else:
            logger.error(
                f"Refund API call failed for "
                f"order {order.order_number}"
            )
            return (
                f"REFUND_FAILED: Could not process refund for order "
                f"{order.order_number}. "
                f"Please escalate to a human agent."
            )

    except Exception as e:
        logger.error(f"Error processing refund for #{cleaned}: {e}")
        return (
            "An error occurred while processing the refund. "
            "Please escalate this to a human agent."
        )


# ------------------------------------------------------------------
# Escalation tool
# ------------------------------------------------------------------

def escalate_to_human(reason: str) -> str:
    """
    Escalates the current conversation to a human support agent.

    Sends a real-time notification to the store owner via Telegram,
    so escalations don't just get logged silently — someone actually
    gets pinged to follow up.

    Use this when:
        - The customer asks to speak to a human
        - A refund tool returns REFUND_NOT_ELIGIBLE or REFUND_FAILED
        - The customer seems frustrated, angry, or upset
        - The request is outside your capabilities
        - You are uncertain about the right course of action

    Args:
        reason: Clear explanation of why escalation is needed.

    Returns:
        Confirmation message to relay to the customer.
    """
    logger.warning(f"Escalating to human | reason: {reason}")

    _notify_owner(reason)

    return (
        f"ESCALATED: {reason} | "
        f"A human agent has been notified and will follow up "
        f"with you shortly. We apologize for any inconvenience."
    )


def _notify_owner(reason: str) -> None:
    """
    Sends a Telegram message to the store owner about an escalation.

    Uses Telegram's raw HTTP API directly (not python-telegram-bot)
    to avoid circular imports with the adapter layer — this keeps
    the tools layer independent of any specific channel.

    Args:
        reason: Why this conversation was escalated.
    """
    if not settings.TELEGRAM_BOT_TOKEN or not settings.OWNER_TELEGRAM_CHAT_ID:
        logger.warning(
            "Cannot notify owner — TELEGRAM_BOT_TOKEN or "
            "OWNER_TELEGRAM_CHAT_ID not configured"
        )
        return

    url = (
        f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}"
        f"/sendMessage"
    )
    message = f"🚨 Escalation needed\n\nReason: {reason}"

    try:
        http_requests.post(
            url,
            json={
                "chat_id": settings.OWNER_TELEGRAM_CHAT_ID,
                "text": message,
            },
            timeout=10,
        )
        logger.info("Owner notified of escalation via Telegram")

    except http_requests.exceptions.RequestException as e:
        logger.error(f"Failed to notify owner: {e}")