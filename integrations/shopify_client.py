"""
integrations/shopify_client.py
-------------------------------
Shopify Admin API client.

This is the ONLY file in the project that:
    - Knows Shopify's URL structure
    - Handles authentication (token exchange)
    - Makes raw HTTP calls to Shopify
    - Understands Shopify's JSON response format

Everything above this layer (tools, orchestrator) calls clean
functions like get_order(order_id) and gets back simple Python
objects — never raw Shopify JSON.

Authentication:
    Shopify's new Dev Dashboard uses OAuth2 client credentials flow.
    We exchange CLIENT_ID + CLIENT_SECRET for a short-lived access token
    (valid ~24 hours). We cache it in memory and refresh when expired.
"""

import requests
from datetime import datetime, timezone
from typing import Optional

from config import settings
from core.models import OrderSummary
from logger import get_logger

logger = get_logger(__name__)


class ShopifyClient:
    """
    Handles all communication with the Shopify Admin REST API.

    Usage:
        client = ShopifyClient()
        order = client.get_order(6688665141445)
        print(order.order_number)  # → "#1001"
    """

    def __init__(self):
        self.store_domain = settings.SHOPIFY_STORE_DOMAIN
        self.api_version = settings.SHOPIFY_API_VERSION
        self.base_url = f"https://{self.store_domain}/admin/api/{self.api_version}"

        # Token cache — avoids fetching a new token on every single API call
        self._access_token: Optional[str] = None
        self._token_expires_at: Optional[datetime] = None

        logger.info(f"ShopifyClient initialized for store: {self.store_domain}")

    # ------------------------------------------------------------------
    # Authentication
    # ------------------------------------------------------------------

    def _get_access_token(self) -> str:
        """
        Returns a valid access token, fetching a new one if expired.

        Shopify tokens last ~24 hours. We cache the token in memory
        and only request a new one when the current one has expired.
        This avoids unnecessary token requests on every API call.

        Returns:
            Valid Shopify Admin API access token string.

        Raises:
            RuntimeError: If token exchange fails.
        """
        now = datetime.now(timezone.utc)

        # Return cached token if still valid
        if self._access_token and self._token_expires_at:
            if now < self._token_expires_at:
                logger.debug("Using cached Shopify access token")
                return self._access_token

        logger.info("Requesting new Shopify access token")

        token_url = f"https://{self.store_domain}/admin/oauth/access_token"
        payload = {
            "client_id": settings.SHOPIFY_CLIENT_ID,
            "client_secret": settings.SHOPIFY_CLIENT_SECRET,
            "grant_type": "client_credentials",
        }

        try:
            response = requests.post(token_url, data=payload, timeout=10)
            logger.debug(f"Token response status: {response.status_code}")
            logger.debug(f"Token response body: {response.text}")
            response.raise_for_status()
            data = response.json()

            self._access_token = data["access_token"]

            # Shopify returns expires_in in seconds — we store the exact expiry time
            # Subtract 60 seconds as a safety buffer so we refresh slightly early
            expires_in = data.get("expires_in", 86400)
            from datetime import timedelta
            self._token_expires_at = now + timedelta(seconds=expires_in - 60)

            logger.info(f"New Shopify token received. Scopes: {data.get('scope', 'unknown')}")
            return self._access_token

        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to get Shopify access token: {e}")
            raise RuntimeError(f"Shopify authentication failed: {e}")

    def _headers(self) -> dict:
        """Returns auth headers for Shopify API requests."""
        return {
            "X-Shopify-Access-Token": self._get_access_token(),
            "Content-Type": "application/json",
        }

    # ------------------------------------------------------------------
    # Internal HTTP helpers
    # ------------------------------------------------------------------

    def _get(self, endpoint: str) -> dict:
        """
        Makes a GET request to the Shopify Admin API.

        Args:
            endpoint: API path e.g. "/orders/123.json"

        Returns:
            Parsed JSON response as a dict.

        Raises:
            RuntimeError: If the request fails or returns an error status.
        """
        url = f"{self.base_url}{endpoint}"
        logger.debug(f"GET {url}")

        try:
            response = requests.get(url, headers=self._headers(), timeout=10)
            response.raise_for_status()
            return response.json()

        except requests.exceptions.HTTPError as e:
            logger.error(f"Shopify API HTTP error: {e} | URL: {url}")
            raise RuntimeError(f"Shopify API error: {e}")

        except requests.exceptions.RequestException as e:
            logger.error(f"Shopify API request failed: {e} | URL: {url}")
            raise RuntimeError(f"Shopify request failed: {e}")

    # ------------------------------------------------------------------
    # Public API methods
    # ------------------------------------------------------------------

    def get_order(self, order_id: int) -> Optional[OrderSummary]:
        """
        Fetches a single order by its Shopify internal ID.

        Args:
            order_id: Shopify's internal numeric order ID
                      (the long number in the URL, NOT the #1001 number)

        Returns:
            OrderSummary if found, None if order doesn't exist.

        Example:
            order = client.get_order(6688665141445)
            print(order.order_number)   # "#1001"
            print(order.status)         # "paid"
        """
        logger.info(f"Fetching order: {order_id}")

        try:
            data = self._get(f"/orders/{order_id}.json")
            return self._parse_order(data["order"])

        except RuntimeError as e:
            logger.error(f"Failed to fetch order {order_id}: {e}")
            return None

    def get_orders_by_email(self, email: str) -> list[OrderSummary]:
        """
        Fetches all orders placed by a customer email address.

        Useful when a customer says "check my orders" without
        providing a specific order number.

        Args:
            email: Customer's email address

        Returns:
            List of OrderSummary objects, newest first.
            Empty list if no orders found.

        Example:
            orders = client.get_orders_by_email("ali@example.com")
            for order in orders:
                print(order.order_number, order.status)
        """
        logger.info(f"Fetching orders for email: {email}")

        try:
            data = self._get(f"/orders.json?email={email}&status=any")
            orders = [self._parse_order(o) for o in data.get("orders", [])]
            logger.info(f"Found {len(orders)} orders for {email}")
            return orders

        except RuntimeError as e:
            logger.error(f"Failed to fetch orders for {email}: {e}")
            return []

    def get_product(self, product_id: int) -> Optional[dict]:
        """
        Fetches basic product info by product ID.

        Returns:
            Dict with title, price, inventory status.
            None if product not found.
        """
        logger.info(f"Fetching product: {product_id}")

        try:
            data = self._get(f"/products/{product_id}.json")
            product = data["product"]

            return {
                "id": product["id"],
                "title": product["title"],
                "status": product["status"],
                "variants": [
                    {
                        "title": v["title"],
                        "price": v["price"],
                        "inventory_quantity": v.get("inventory_quantity", 0),
                    }
                    for v in product.get("variants", [])
                ],
            }

        except RuntimeError as e:
            logger.error(f"Failed to fetch product {product_id}: {e}")
            return None

    # ------------------------------------------------------------------
    # Private parsing helpers
    # ------------------------------------------------------------------

    def _parse_order(self, raw: dict) -> OrderSummary:
        """
        Converts raw Shopify order JSON into a clean OrderSummary.

        This is where we "throw away" the 100+ fields Shopify returns
        and keep only what our agent actually needs.

        Args:
            raw: Raw order dict from Shopify API response

        Returns:
            Clean OrderSummary dataclass instance
        """
        # Extract product names from line items
        line_items = [item.get("name", "Unknown item") for item in raw.get("line_items", [])]

        # Parse created_at string into timezone-aware datetime
        created_at_str = raw.get("created_at", "")
        try:
            created_at = datetime.fromisoformat(created_at_str)
        except (ValueError, TypeError):
            logger.warning(f"Could not parse created_at: {created_at_str}")
            created_at = datetime.now(timezone.utc)

        # Extract customer email safely (customer may be None for draft orders)
        customer = raw.get("customer") or {}
        customer_email = customer.get("email")

        return OrderSummary(
            order_id=raw["id"],
            order_number=raw.get("name", f"#{raw['id']}"),
            status=raw.get("financial_status", "unknown"),
            fulfillment_status=raw.get("fulfillment_status"),
            total_price=float(raw.get("current_total_price", 0)),
            currency=raw.get("currency", "USD"),
            line_items=line_items,
            created_at=created_at,
            customer_email=customer_email,
        )