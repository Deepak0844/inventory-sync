import json
from typing import Any

import httpx
import pytest

from app.shopify.client import ShopifyClient, ShopifyError
from tests.fakes import FakeClock

VARIANT = "gid://shopify/ProductVariant/1"


class FakeShopify:
    """Answers the three GraphQL operations the client uses and records them."""

    def __init__(self, tracked: bool = False) -> None:
        self.tracked = tracked
        self.calls: list[dict[str, Any]] = []
        self.failures: list[httpx.Response | Exception] = []
        self.locations: list[dict[str, str]] = [{"id": "gid://shopify/Location/9"}]
        self.user_errors: list[str] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if self.failures:
            failure = self.failures.pop(0)
            if isinstance(failure, Exception):
                raise failure
            return failure
        body = json.loads(request.content)
        query: str = body["query"]
        self.calls.append({"query": query, "variables": body["variables"],
                           "token": request.headers["X-Shopify-Access-Token"]})
        if "inventorySetQuantities" in query:
            errors = [{"message": m} for m in self.user_errors]
            data: dict[str, Any] = {"inventorySetQuantities": {"userErrors": errors}}
        elif "inventoryItemUpdate" in query:
            self.tracked = True
            data = {"inventoryItemUpdate": {"userErrors": []}}
        elif "locations" in query:
            data = {"locations": {"nodes": self.locations}}
        else:
            data = {"productVariant": {"inventoryItem": {"id": "gid://shopify/InventoryItem/5",
                                                          "tracked": self.tracked}}}
        return httpx.Response(200, json={"data": data})

    def operations(self) -> list[str]:
        names = ("inventorySetQuantities", "inventoryItemUpdate", "locations", "productVariant")
        return [n for c in self.calls for n in names if n in c["query"]]


def client_for(shopify: FakeShopify, clock: FakeClock | None = None) -> ShopifyClient:
    return ShopifyClient(
        shop="dev-store.myshopify.com",
        access_token="tok",
        transport=httpx.MockTransport(shopify),
        clock=clock or FakeClock(),
    )


def test_turns_tracking_on_before_setting_quantity() -> None:
    shopify = FakeShopify(tracked=False)
    client_for(shopify).set_available(VARIANT, 0)
    ops = shopify.operations()
    assert ops.index("inventoryItemUpdate") < ops.index("inventorySetQuantities")


def test_leaves_tracking_alone_when_already_on() -> None:
    shopify = FakeShopify(tracked=True)
    client_for(shopify).set_available(VARIANT, 0)
    assert "inventoryItemUpdate" not in shopify.operations()


def test_sets_the_requested_quantity_at_the_location() -> None:
    shopify = FakeShopify(tracked=True)
    client_for(shopify).set_available(VARIANT, 100)
    sent = shopify.calls[-1]["variables"]["input"]["quantities"][0]
    assert sent == {"inventoryItemId": "gid://shopify/InventoryItem/5",
                    "locationId": "gid://shopify/Location/9", "quantity": 100}


def test_sends_the_access_token_header() -> None:
    shopify = FakeShopify(tracked=True)
    client_for(shopify).set_available(VARIANT, 0)
    assert {c["token"] for c in shopify.calls} == {"tok"}


def test_user_errors_raise_a_shopify_error() -> None:
    shopify = FakeShopify(tracked=True)
    shopify.user_errors = ["Location not stocked"]
    with pytest.raises(ShopifyError, match="Location not stocked"):
        client_for(shopify).set_available(VARIANT, 0)


def test_retries_throttling_with_backoff_then_succeeds() -> None:
    shopify = FakeShopify(tracked=True)
    shopify.failures = [httpx.Response(429), httpx.Response(503)]
    clock = FakeClock()
    client_for(shopify, clock).set_available(VARIANT, 0)
    assert clock.now() > 0
    assert "inventorySetQuantities" in shopify.operations()


def test_gives_up_after_the_retries_are_used() -> None:
    shopify = FakeShopify(tracked=True)
    shopify.failures = [httpx.Response(503)] * 10
    with pytest.raises(ShopifyError, match="503"):
        client_for(shopify).set_available(VARIANT, 0)


def test_unknown_variant_raises() -> None:
    def no_variant(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": {"productVariant": None}})

    client = ShopifyClient("s.myshopify.com", "tok", httpx.MockTransport(no_variant), FakeClock())
    with pytest.raises(ShopifyError, match="not found"):
        client.set_available(VARIANT, 0)


def test_throttling_reported_inside_a_200_response_is_retried() -> None:
    shopify = FakeShopify(tracked=True)
    throttled = {"errors": [{"message": "Throttled", "extensions": {"code": "THROTTLED"}}]}
    shopify.failures = [httpx.Response(200, json=throttled)]
    clock = FakeClock()
    client_for(shopify, clock).set_available(VARIANT, 0)
    assert clock.now() > 0
    assert "inventorySetQuantities" in shopify.operations()


def test_connection_error_is_retried() -> None:
    shopify = FakeShopify(tracked=True)
    shopify.failures = [httpx.ConnectError("reset")]
    client_for(shopify).set_available(VARIANT, 0)
    assert "inventorySetQuantities" in shopify.operations()


def test_persistent_connection_error_becomes_a_shopify_error() -> None:
    shopify = FakeShopify(tracked=True)
    shopify.failures = [httpx.ConnectError("reset")] * 10
    with pytest.raises(ShopifyError, match="could not reach"):
        client_for(shopify).set_available(VARIANT, 0)


def test_shop_without_locations_raises_a_shopify_error() -> None:
    shopify = FakeShopify(tracked=True)
    shopify.locations = []
    with pytest.raises(ShopifyError, match="no location"):
        client_for(shopify).set_available(VARIANT, 0)
