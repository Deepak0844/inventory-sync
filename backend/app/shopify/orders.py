"""Reading recent Shopify orders so orders with a risky Variant can be flagged.

Polling, not webhooks: webhooks need a public URL. Not responsible for deciding
which orders to flag (`app.engine`) or for storing them.
"""

from dataclasses import dataclass
from typing import Protocol

from app.shopify.client import ShopifyClient

_ORDERS = """
query($query: String!, $after: String) {
  orders(first: 50, query: $query, after: $after, sortKey: CREATED_AT) {
    nodes { id name createdAt lineItems(first: 100) { nodes { variant { id } } } }
    pageInfo { hasNextPage endCursor }
  }
}
"""


@dataclass(frozen=True)
class Order:
    """An order reduced to what flagging needs."""

    id: str
    name: str
    created_at: str
    variant_ids: tuple[str, ...]


class OrderReader(Protocol):
    """What the rest of the app needs to learn about new orders."""

    def recent_orders(self, since_iso: str) -> list[Order]:
        """Return orders created at or after `since_iso`, oldest first."""
        ...


class ShopifyOrderReader:
    """Reads orders through the Admin GraphQL API (needs the `read_orders` scope)."""

    def __init__(self, client: ShopifyClient) -> None:
        self._client = client

    def recent_orders(self, since_iso: str) -> list[Order]:
        """Return orders created at or after `since_iso`, oldest first.

        Follows pages until Shopify reports no more. Line items whose Variant was
        deleted are skipped, since there is nothing to flag them against.

        Args:
            since_iso: ISO 8601 timestamp, for example "2026-11-01T00:00:00Z".

        Returns:
            The matching orders.

        Raises:
            ShopifyError: if a request is rejected or retries are exhausted.
        """
        orders: list[Order] = []
        cursor: str | None = None
        while True:
            data = self._client.graphql(
                _ORDERS, {"query": f"created_at:>={since_iso}", "after": cursor}
            )["orders"]
            for node in data["nodes"]:
                variants = tuple(
                    item["variant"]["id"]
                    for item in node["lineItems"]["nodes"]
                    if item["variant"] is not None
                )
                orders.append(Order(node["id"], node["name"], node["createdAt"], variants))
            if not data["pageInfo"]["hasNextPage"]:
                return orders
            cursor = data["pageInfo"]["endCursor"]
