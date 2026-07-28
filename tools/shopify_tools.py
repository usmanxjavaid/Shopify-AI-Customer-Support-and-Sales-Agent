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
from core.guardrails import determine_refund_path, RefundPath
from persistence.queries import create_pending_return
from persistence.queries import get_open_ticket, create_ticket, add_ticket_message
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
    order_number: str,
    reason: str,
    verified_email: str,
    channel: str = "unknown",
    user_id: str = "unknown",
) -> str:
    """
    Processes a refund request by routing it through the correct
    automated path based on real shipment status:

        - Not shipped yet        -> refunded immediately
        - Shipped, no tracking   -> fulfillment cancelled, then refunded
                                     (only if cancellation is confirmed)
        - Actually shipped       -> a return is started; refund happens
                                     ONLY after a human confirms the
                                     item has physically been returned

    Args:
        order_number:   The order number to refund e.g. "1001".
        reason:         The customer's stated reason for the refund.
        verified_email: Email confirmed via verify_customer_email.
        channel:        Injected automatically by the orchestrator —
                        NOT something the LLM should pass.
        user_id:        Injected automatically by the orchestrator —
                        NOT something the LLM should pass.

    Returns:
        Plain text result for the LLM to relay to the customer.
    """
    cleaned = order_number.strip().lstrip("#").strip()
    logger.info(f"Refund requested for order #{cleaned} | reason: {reason}")

    try:
        orders = _client.get_orders_by_number(cleaned)
        if not orders:
            return f"Order #{cleaned} could not be found."

        order = orders[0]

        if (
            not order.customer_email
            or order.customer_email.strip().lower() != verified_email.strip().lower()
        ):
            return (
                "REFUND_NOT_ELIGIBLE: Identity could not be verified "
                "for this order. Please escalate to a human agent."
            )

        path, path_reason = determine_refund_path(
            order_total=order.total_price,
            order_fulfilled_at=order.created_at,
            fulfillment_status=order.fulfillment_status,
            financial_status=order.status,
            tracking_number=order.tracking_number,
        )

        if path == RefundPath.ALREADY_REFUNDED:
            return f"REFUND_NOT_ELIGIBLE: {path_reason}"

        if path == RefundPath.NOT_PAID:
            return f"REFUND_NOT_ELIGIBLE: {path_reason} Please escalate to a human agent."

        if path == RefundPath.NOT_ELIGIBLE:
            return f"REFUND_NOT_ELIGIBLE: {path_reason} Please escalate to a human agent."

        if path == RefundPath.AUTO_REFUND:
            success = _client.create_refund(order.order_id, order.total_price, reason)
            if success:
                return (
                    f"Refund successfully initiated for order {order.order_number}. "
                    f"{order.currency} {order.total_price:.2f} will be returned "
                    f"within 5-7 business days."
                )
            return "REFUND_FAILED: Could not process refund. Please escalate."

        if path == RefundPath.CANCEL_AND_REFUND:
            cancel_success = False
            if order.fulfillment_id:
                cancel_success = _client.cancel_order_fulfillment(order.order_id)

            if not cancel_success:
                logger.warning(
                    f"Could not confirm fulfillment cancellation for order "
                    f"{order.order_number} — refusing to refund automatically."
                )
                return (
                    "REFUND_NOT_ELIGIBLE: Could not confirm the order was "
                    "stopped before shipping. Please escalate to a human agent "
                    "for manual verification before refunding."
                )

            success = _client.create_refund(order.order_id, order.total_price, reason)
            if success:
                return (
                    f"Your order {order.order_number} hadn't actually shipped yet, "
                    f"so we've cancelled it and refunded {order.currency} "
                    f"{order.total_price:.2f}, returning within 5-7 business days."
                )
            return "REFUND_FAILED: Could not process refund. Please escalate."

        if path == RefundPath.REQUIRES_RETURN:
            create_pending_return(
                order_number=order.order_number,
                channel=channel,
                user_id=user_id,
                customer_email=verified_email,
                tracking_number=order.tracking_number,
            )
            return (
                f"RETURN_REQUIRED: Order {order.order_number} has already shipped, "
                f"so we can't refund it until we receive the item back. Please ship "
                f"it back to us — once it arrives, your refund of {order.currency} "
                f"{order.total_price:.2f} will be processed automatically. "
                f"Our team will follow up with return shipping instructions."
            )

        return "REFUND_FAILED: Unexpected state. Please escalate to a human agent."

    except Exception as e:
        logger.error(f"Error processing refund for #{cleaned}: {e}")
        return "An error occurred while processing the refund. Please escalate."

# ------------------------------------------------------------------
# Escalation tool
# ------------------------------------------------------------------

def escalate_to_human(
    reason: str,
    customer_email: str = None,
    channel: str = "unknown",
    user_id: str = "unknown",
) -> str:
    """
    Escalates the conversation to a human agent, creating a proper
    support ticket. If a ticket is already open for this customer,
    adds to it instead of creating a duplicate.

    Once escalated, the AI will stop responding to this customer
    until a human resolves the ticket — this tool is the handoff
    point, not just a notification.

    Args:
        reason: Clear explanation of why escalation is needed.
        customer_email: Customer's email, if available (required
                        in practice for web channel customers).
        channel: Injected automatically by the orchestrator.
        user_id: Injected automatically by the orchestrator.

    Returns:
        Confirmation message to relay to the customer.
    """
    logger.warning(f"Escalating {channel}:{user_id} | reason: {reason}")

    existing = get_open_ticket(channel, user_id)
    if existing:
        add_ticket_message(existing["id"], "system", f"Re-escalated: {reason}")
        ticket_id = existing["id"]
    else:
        ticket_id = create_ticket(channel, user_id, customer_email, reason)
        _send_ticket_notifications(ticket_id, channel, reason, customer_email)

    return (
        f"ESCALATED: Ticket #{ticket_id} created. A human agent has "
        f"been notified and will follow up with you shortly"
        f"{' by email' if customer_email else ''}. "
        f"We apologize for any inconvenience."
    )


def _send_ticket_notifications(ticket_id: int, channel: str, reason: str, customer_email: str) -> None:
    """Notifies the owner of a new ticket via Telegram and email."""
    if settings.TELEGRAM_BOT_TOKEN and settings.OWNER_TELEGRAM_CHAT_ID:
        try:
            http_requests.post(
                f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage",
                json={
                    "chat_id": settings.OWNER_TELEGRAM_CHAT_ID,
                    "text": f"🎫 New ticket #{ticket_id}\n\n{reason}",
                },
                timeout=10,
            )
        except http_requests.exceptions.RequestException as e:
            logger.error(f"Telegram ticket notify failed: {e}")

    if settings.RESEND_API_KEY and settings.OWNER_EMAIL:
        base_address = settings.RESEND_INBOUND_ADDRESS
        local_part, domain_part = base_address.split("@")
        reply_to = f"{local_part}+ticket{ticket_id}@{domain_part}"

        try:
            http_requests.post(
                "https://api.resend.com/emails",
                headers={"Authorization": f"Bearer {settings.RESEND_API_KEY}"},
                json={
                    "from": "Velvora Support <onboarding@resend.dev>",
                    "to": [settings.OWNER_EMAIL],
                    "reply_to": reply_to,
                    "subject": f"Ticket #{ticket_id}: {reason[:60]}",
                    "text": (
                        f"{reason}\n\nCustomer email: {customer_email or 'not provided'}\n\n"
                        f"Reply to this email to respond directly to the customer."
                    ),
                },
                timeout=10,
            )
            logger.info(f"Email notification sent for ticket #{ticket_id}")
        except http_requests.exceptions.RequestException as e:
            logger.error(f"Email ticket notify failed: {e}")
