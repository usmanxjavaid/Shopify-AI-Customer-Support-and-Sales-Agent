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
functions and gets back simple Python objects — never raw JSON.

Authentication:
    Uses OAuth2 client credentials flow.
    Exchanges CLIENT_ID + CLIENT_SECRET for a short-lived access
    token (~24 hours). Cached in memory, refreshed when expired.
"""

import requests
from datetime import datetime, timezone, timedelta
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
        self.base_url = (
            f"https://{self.store_domain}/admin/api/{self.api_version}"
        )

        # Token cache
        self._access_token: Optional[str] = None
        self._token_expires_at: Optional[datetime] = None

        logger.info(
            f"ShopifyClient initialized for store: {self.store_domain}"
        )

    # ------------------------------------------------------------------
    # Authentication
    # ------------------------------------------------------------------

    def _get_access_token(self) -> str:
        """
        Returns a valid access token, fetching a new one if expired.

        Tokens last ~24 hours. We cache in memory and only request
        a new one when the current one has expired.

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

        token_url = (
            f"https://{self.store_domain}/admin/oauth/access_token"
        )
        payload = {
            "client_id": settings.SHOPIFY_CLIENT_ID,
            "client_secret": settings.SHOPIFY_CLIENT_SECRET,
            "grant_type": "client_credentials",
        }

        try:
            response = requests.post(
                token_url, data=payload, timeout=10
            )
            response.raise_for_status()
            data = response.json()

            self._access_token = data["access_token"]

            expires_in = data.get("expires_in", 86400)
            self._token_expires_at = now + timedelta(
                seconds=expires_in - 60
            )

            logger.info(
                f"New Shopify token received. "
                f"Scopes: {data.get('scope', 'unknown')}"
            )
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
            RuntimeError: If the request fails.
        """
        url = f"{self.base_url}{endpoint}"
        logger.debug(f"GET {url}")

        try:
            response = requests.get(
                url, headers=self._headers(), timeout=10
            )
            response.raise_for_status()
            return response.json()

        except requests.exceptions.HTTPError as e:
            logger.error(f"Shopify API HTTP error: {e} | URL: {url}")
            raise RuntimeError(f"Shopify API error: {e}")

        except requests.exceptions.RequestException as e:
            logger.error(
                f"Shopify API request failed: {e} | URL: {url}"
            )
            raise RuntimeError(f"Shopify request failed: {e}")

    def _post(self, endpoint: str, payload: dict) -> dict:
        """
        Makes a POST request to the Shopify Admin API.

        Args:
            endpoint: API path e.g. "/orders/123/refunds.json"
            payload:  Request body as a dict.

        Returns:
            Parsed JSON response as a dict.

        Raises:
            RuntimeError: If the request fails.
        """
        url = f"{self.base_url}{endpoint}"
        logger.debug(f"POST {url}")

        try:
            response = requests.post(
                url, headers=self._headers(), json=payload, timeout=10
            )
            response.raise_for_status()
            return response.json()

        except requests.exceptions.HTTPError as e:
            logger.error(f"Shopify API HTTP error: {e} | URL: {url}")
            raise RuntimeError(f"Shopify API error: {e}")

        except requests.exceptions.RequestException as e:
            logger.error(
                f"Shopify API request failed: {e} | URL: {url}"
            )
            raise RuntimeError(f"Shopify request failed: {e}")

    # ------------------------------------------------------------------
    # Public API methods
    # ------------------------------------------------------------------

    def get_order(self, order_id: int) -> Optional[OrderSummary]:
        """
        Fetches a single order by its Shopify internal ID.

        Args:
            order_id: Shopify's internal numeric order ID
                      (the long number in the URL, NOT #1001)

        Returns:
            OrderSummary if found, None if order doesn't exist.
        """
        logger.info(f"Fetching order by ID: {order_id}")

        try:
            data = self._get(f"/orders/{order_id}.json")
            return self._parse_order(data["order"])

        except RuntimeError as e:
            logger.error(f"Failed to fetch order {order_id}: {e}")
            return None

    def get_orders_by_email(self, email: str) -> list[OrderSummary]:
        """
        Fetches all orders placed by a customer email address.

        Args:
            email: Customer's email address.

        Returns:
            List of OrderSummary objects, newest first.
            Empty list if no orders found.
        """
        logger.info(f"Fetching orders for email: {email}")

        try:
            data = self._get(
                f"/orders.json?email={email}&status=any"
            )
            orders = [
                self._parse_order(o) for o in data.get("orders", [])
            ]
            logger.info(f"Found {len(orders)} orders for {email}")
            return orders

        except RuntimeError as e:
            logger.error(f"Failed to fetch orders for {email}: {e}")
            return []

    def get_orders_by_number(
        self, order_number: str
    ) -> list[OrderSummary]:
        """
        Fetches orders matching a given order number.

        Shopify has no direct "search by order number" endpoint,
        so we fetch recent orders and filter by the name field.

        Args:
            order_number: Order number without # e.g. "1001"

        Returns:
            List of matching OrderSummary objects (usually one).
        """
        logger.info(f"Searching for order number: #{order_number}")

        try:
            data = self._get("/orders.json?status=any&limit=250")
            all_orders = [
                self._parse_order(o) for o in data.get("orders", [])
            ]

            # Match by order number — Shopify stores it as "#1001"
            matches = [
                o for o in all_orders
                if o.order_number.lstrip("#") == order_number
            ]

            logger.info(
                f"Found {len(matches)} orders matching #{order_number}"
            )
            return matches

        except RuntimeError as e:
            logger.error(f"Failed to search orders by number: {e}")
            return []

    def get_product_by_name(
        self, product_name: str
    ) -> Optional[dict]:
        """
        Fetches basic product info by searching product title.

        Args:
            product_name: Product name or partial name.

        Returns:
            Dict with title, status, variants. None if not found.
        """
        logger.info(f"Fetching product by name: {product_name}")

        try:
            data = self._get(
                f"/products.json?title={product_name}&limit=5"
            )
            products = data.get("products", [])

            if not products:
                logger.warning(
                    f"No product found matching: {product_name}"
                )
                return None

            product = products[0]

            return {
                "id": product["id"],
                "title": product["title"],
                "status": product["status"],
                "variants": [
                    {
                        "title": v["title"],
                        "price": v["price"],
                        "inventory_quantity": v.get(
                            "inventory_quantity", 0
                        ),
                    }
                    for v in product.get("variants", [])
                ],
            }

        except RuntimeError as e:
            logger.error(
                f"Failed to fetch product '{product_name}': {e}"
            )
            return None

    def create_refund(
        self,
        order_id: int,
        amount: float,
        reason: str,
    ) -> bool:
        """
        Issues a refund for an order via Shopify API.

        Only called after guardrails have confirmed eligibility.

        Args:
            order_id: Shopify internal order ID.
            amount:   Amount to refund in store currency.
            reason:   Customer's stated reason (stored on order).

        Returns:
            True if refund was created successfully, False otherwise.
        """
        logger.info(
            f"Creating refund | order_id={order_id} amount={amount}"
        )

        payload = {
            "refund": {
                "notify": True,
                "note": reason,
                "transactions": [
                    {
                        "kind": "refund",
                        "amount": str(amount),
                        "gateway": "manual",
                    }
                ],
            }
        }

        try:
            self._post(
                f"/orders/{order_id}/refunds.json", payload
            )
            logger.info(
                f"Refund created successfully for order {order_id}"
            )
            return True

        except RuntimeError as e:
            logger.error(
                f"Failed to create refund for order {order_id}: {e}"
            )
            return False

    # ------------------------------------------------------------------
    # Private parsing helpers
    # ------------------------------------------------------------------

    def _parse_order(self, raw: dict) -> OrderSummary:
        """
        Converts raw Shopify order JSON into a clean OrderSummary.

        Args:
            raw: Raw order dict from Shopify API response.

        Returns:
            Clean OrderSummary dataclass instance.
        """
        line_items = [
            item.get("name", "Unknown item")
            for item in raw.get("line_items", [])
        ]

        created_at_str = raw.get("created_at", "")
        try:
            created_at = datetime.fromisoformat(created_at_str)
        except (ValueError, TypeError):
            logger.warning(
                f"Could not parse created_at: {created_at_str}"
            )
            created_at = datetime.now(timezone.utc)

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