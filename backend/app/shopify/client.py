"""Shopify Admin GraphQL client for inventory writes.

Not responsible for deciding when to write (the decision engine) or for
obtaining the access token.
"""

from typing import Any, Protocol

import httpx

from app.core.clock import Clock

API_VERSION = "2025-10"
MAX_ATTEMPTS = 4
BACKOFF_SECONDS = 1.0

_VARIANT = """
query($id: ID!) { productVariant(id: $id) { inventoryItem { id tracked } } }
"""
_LOCATION = "query { locations(first: 1) { nodes { id } } }"
_TRACK = """
mutation($id: ID!) {
  inventoryItemUpdate(id: $id, input: {tracked: true}) { userErrors { message } }
}
"""
_SET = """
mutation($input: InventorySetQuantitiesInput!) {
  inventorySetQuantities(input: $input) { userErrors { message } }
}
"""


class ShopifyError(Exception):
    """A Shopify call failed after retries, or Shopify rejected it."""


class InventoryWriter(Protocol):
    """What the rest of the app needs from Shopify."""

    def set_available(self, variant_id: str, quantity: int) -> None:
        """Set the available quantity of a Variant, turning tracking on if needed."""
        ...


class ShopifyClient:
    """Admin API client. Retries throttling and server errors with backoff."""

    def __init__(
        self, shop: str, access_token: str, transport: httpx.BaseTransport, clock: Clock
    ) -> None:
        self._http = httpx.Client(
            base_url=f"https://{shop}/admin/api/{API_VERSION}",
            headers={"X-Shopify-Access-Token": access_token},
            transport=transport,
        )
        self._clock = clock

    def set_available(self, variant_id: str, quantity: int) -> None:
        """Set a Variant's available quantity at the shop's first location.

        Turns inventory tracking on first when it is off.

        Raises:
            ShopifyError: if the Variant is unknown, Shopify returns errors, or
                retries are exhausted.
        """
        variant = self._query(_VARIANT, {"id": variant_id})["productVariant"]
        if variant is None:
            raise ShopifyError(f"Variant {variant_id} not found")
        item = variant["inventoryItem"]
        if not item["tracked"]:
            self._mutate(_TRACK, {"id": item["id"]}, "inventoryItemUpdate")
        locations = self._query(_LOCATION, {})["locations"]["nodes"]
        if not locations:
            raise ShopifyError("shop has no location to stock inventory at")
        location = locations[0]["id"]
        quantities = [{"inventoryItemId": item["id"], "locationId": location, "quantity": quantity}]
        self._mutate(
            _SET,
            {
                "input": {
                    "name": "available",
                    "reason": "correction",
                    "ignoreCompareQuantity": True,
                    "quantities": quantities,
                }
            },
            "inventorySetQuantities",
        )

    def graphql(self, query: str, variables: dict[str, Any]) -> dict[str, Any]:
        """Run a GraphQL query with the client's retry and backoff, returning `data`.

        Shared with the order reader so both retry throttling the same way.

        Raises:
            ShopifyError: on a rejected request, GraphQL errors, or exhausted retries.
        """
        return self._query(query, variables)

    def _mutate(self, query: str, variables: dict[str, Any], field: str) -> None:
        errors = self._query(query, variables)[field]["userErrors"]
        if errors:
            raise ShopifyError("; ".join(e["message"] for e in errors))

    def _query(self, query: str, variables: dict[str, Any]) -> dict[str, Any]:
        payload = {"query": query, "variables": variables}
        for attempt in range(MAX_ATTEMPTS):
            last = attempt == MAX_ATTEMPTS - 1
            try:
                response = self._http.post("/graphql.json", json=payload)
            except httpx.TransportError as exc:
                if last:
                    raise ShopifyError("could not reach Shopify after retries") from exc
                self._clock.sleep(BACKOFF_SECONDS * 2**attempt)
                continue
            if response.status_code == 429 or response.status_code >= 500:
                if last:
                    raise ShopifyError(f"Shopify returned {response.status_code} after retries")
                self._clock.sleep(BACKOFF_SECONDS * 2**attempt)
                continue
            if response.status_code != 200:
                raise ShopifyError(f"Shopify returned {response.status_code}")
            body = response.json()
            errors = body.get("errors")
            if errors:
                # Shopify reports GraphQL throttling as a 200 with this error code.
                if _is_throttled(errors) and not last:
                    self._clock.sleep(BACKOFF_SECONDS * 2**attempt)
                    continue
                raise ShopifyError(str(errors))
            data: dict[str, Any] = body["data"]
            return data
        raise ShopifyError("unreachable")  # pragma: no cover


def _is_throttled(errors: list[dict[str, Any]]) -> bool:
    return any(e.get("extensions", {}).get("code") == "THROTTLED" for e in errors)
