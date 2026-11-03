"""Reading recent Shopify orders so orders with a risky Variant can be flagged.

Polling, not webhooks: webhooks need a public URL. Not responsible for deciding
which orders to flag (`app.engine`) or for storing them.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from app.shopify.client import ShopifyClient

_ORDERS = """
query($query: String!, $after: String) {
  orders(first: 20, query: $query, after: $after, sortKey: CREATED_AT) {
    nodes {
      id name createdAt
      lineItems(first: 40) { nodes { variant { id } } pageInfo { hasNextPage } }
    }
    pageInfo { hasNextPage endCursor }
  }
}
"""


class InvalidSince(ValueError):
    """The `since` timestamp is not an ISO 8601 date and time."""


@dataclass(frozen=True)
class Order:
    """An order reduced to what flagging needs.

    `lines_truncated` is True when the order has more line items than were
    fetched, so `variant_ids` is incomplete. Callers should treat such an order
    as needing verification rather than assume it is clear.
    """

    id: str
    name: str
    created_at: str
    variant_ids: tuple[str, ...]
    lines_truncated: bool = False


def _normalise_since(since_iso: str) -> str:
    """Return `since_iso` as UTC `YYYY-MM-DDTHH:MM:SSZ`, or raise InvalidSince."""
    try:
        moment = datetime.fromisoformat(since_iso.replace("Z", "+00:00"))
    except ValueError as exc:
        raise InvalidSince(f"not an ISO 8601 timestamp: {since_iso!r}") from exc
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


class OrderReader(Protocol):
    """What the rest of the app needs to learn about new orders."""

    def recent_orders(self, since_iso: str) -> list[Order]:
        """Return orders created at or after `since_iso`, oldest first.

        The filter is inclusive, so the boundary order is returned again on the
        next poll; callers must de-duplicate by `Order.id`.
        """
        ...


class ShopifyOrderReader:
    """Reads orders through the Admin GraphQL API (needs the `read_orders` scope)."""

    def __init__(self, client: ShopifyClient) -> None:
        self._client = client

    def recent_orders(self, since_iso: str) -> list[Order]:
        """Return orders created at or after `since_iso`, oldest first.

        Follows pages until Shopify reports no more. Line items whose Variant was
        deleted are skipped, since there is nothing to flag them against.

        The filter is inclusive. Polling from the last order's own time returns
        that order again, so callers must de-duplicate by `Order.id`.

        Args:
            since_iso: ISO 8601 timestamp, for example "2026-11-01T00:00:00Z".
                Any offset is accepted and converted to UTC; a time without an
                offset is taken as UTC.

        Returns:
            The matching orders. An order with more line items than fetched has
            `lines_truncated` set.

        Raises:
            InvalidSince: if `since_iso` is not a valid ISO 8601 timestamp.
            ShopifyError: if a request is rejected or retries are exhausted.
        """
        since = _normalise_since(since_iso)
        orders: list[Order] = []
        cursor: str | None = None
        while True:
            data = self._client.graphql(
                _ORDERS, {"query": f'created_at:>="{since}"', "after": cursor}
            )["orders"]
            for node in data["nodes"]:
                variants = tuple(
                    item["variant"]["id"]
                    for item in node["lineItems"]["nodes"]
                    if item["variant"] is not None
                )
                truncated = bool(node["lineItems"]["pageInfo"]["hasNextPage"])
                orders.append(
                    Order(node["id"], node["name"], node["createdAt"], variants, truncated)
                )
            if not data["pageInfo"]["hasNextPage"]:
                return orders
            cursor = data["pageInfo"]["endCursor"]
