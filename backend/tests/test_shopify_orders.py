import json
from typing import Any

import httpx
import pytest

from app.shopify.client import ShopifyClient, ShopifyError
from app.shopify.orders import InvalidSince, Order, ShopifyOrderReader
from tests.fakes import FakeClock


def order_node(number: int, variants: list[str | None], more_lines: bool = False) -> dict[str, Any]:
    return {
        "id": f"gid://shopify/Order/{number}",
        "name": f"#{number}",
        "createdAt": f"2026-11-0{number}T10:00:00Z",
        "lineItems": {
            "nodes": [{"variant": None if v is None else {"id": v}} for v in variants],
            "pageInfo": {"hasNextPage": more_lines},
        },
    }


class FakeOrders:
    """Serves pages of orders and records the variables of each request."""

    def __init__(self, pages: list[list[dict[str, Any]]]) -> None:
        self.pages = pages
        self.requests: list[dict[str, Any]] = []
        self.queries: list[str] = []
        self.failures: list[httpx.Response] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if self.failures:
            return self.failures.pop(0)
        body = json.loads(request.content)
        self.queries.append(body["query"])
        variables = body["variables"]
        self.requests.append(variables)
        index = len(self.requests) - 1
        data = {"orders": {
            "nodes": self.pages[index],
            "pageInfo": {"hasNextPage": index < len(self.pages) - 1, "endCursor": f"c{index}"},
        }}
        return httpx.Response(200, json={"data": data})


def reader_for(fake: FakeOrders, clock: FakeClock | None = None) -> ShopifyOrderReader:
    client = ShopifyClient("s.myshopify.com", "tok", httpx.MockTransport(fake),
                           clock or FakeClock())
    return ShopifyOrderReader(client)


def test_reads_orders_with_their_variant_ids() -> None:
    fake = FakeOrders([[order_node(1, ["gid://shopify/ProductVariant/1",
                                       "gid://shopify/ProductVariant/2"])]])
    orders = reader_for(fake).recent_orders("2026-11-01T00:00:00Z")
    assert orders == [Order("gid://shopify/Order/1", "#1", "2026-11-01T10:00:00Z",
                            ("gid://shopify/ProductVariant/1", "gid://shopify/ProductVariant/2"),
                            lines_truncated=False)]


def test_asks_only_for_orders_since_the_given_time() -> None:
    fake = FakeOrders([[]])
    reader_for(fake).recent_orders("2026-11-01T00:00:00Z")
    assert fake.requests[0]["query"] == "created_at:>=\"2026-11-01T00:00:00Z\""


def test_follows_pages_until_the_last_one() -> None:
    fake = FakeOrders([[order_node(1, ["v1"])], [order_node(2, ["v2"])]])
    orders = reader_for(fake).recent_orders("2026-11-01T00:00:00Z")
    assert [o.name for o in orders] == ["#1", "#2"]
    assert fake.requests[1]["after"] == "c0"
    assert fake.requests[0]["after"] is None


def test_line_item_whose_variant_was_deleted_is_skipped() -> None:
    fake = FakeOrders([[order_node(1, [None, "v1"])]])
    assert reader_for(fake).recent_orders("2026-11-01T00:00:00Z")[0].variant_ids == ("v1",)


def test_throttling_is_retried_with_backoff() -> None:
    fake = FakeOrders([[order_node(1, ["v1"])]])
    fake.failures = [httpx.Response(429), httpx.Response(503)]
    clock = FakeClock()
    assert len(reader_for(fake, clock).recent_orders("2026-11-01T00:00:00Z")) == 1
    assert clock.now() > 0


def test_a_rejected_request_raises_a_shopify_error() -> None:
    fake = FakeOrders([[]])
    fake.failures = [httpx.Response(403)]
    with pytest.raises(ShopifyError, match="403"):
        reader_for(fake).recent_orders("2026-11-01T00:00:00Z")


def test_query_asks_for_a_cost_friendly_page_size() -> None:
    fake = FakeOrders([[]])
    reader_for(fake).recent_orders("2026-11-01T00:00:00Z")
    assert "orders(first: 20" in fake.queries[0]
    assert "lineItems(first: 40)" in fake.queries[0]


def test_order_with_more_line_items_than_fetched_is_marked_truncated() -> None:
    fake = FakeOrders([[order_node(1, ["v1"], more_lines=True), order_node(2, ["v2"])]])
    orders = reader_for(fake).recent_orders("2026-11-01T00:00:00Z")
    assert [o.lines_truncated for o in orders] == [True, False]


@pytest.mark.parametrize(
    ("given", "sent"),
    [
        ("2026-11-01T00:00:00Z", "2026-11-01T00:00:00Z"),
        ("2026-11-01T05:30:00+05:30", "2026-11-01T00:00:00Z"),
        ("2026-11-01 00:00:00+00:00", "2026-11-01T00:00:00Z"),
        ("2026-11-01T00:00:00.123456Z", "2026-11-01T00:00:00Z"),
    ],
)
def test_since_is_normalised_to_utc_and_quoted(given: str, sent: str) -> None:
    fake = FakeOrders([[]])
    reader_for(fake).recent_orders(given)
    assert fake.requests[0]["query"] == f'created_at:>="{sent}"'


@pytest.mark.parametrize("bad", ["yesterday", "", '2026-11-01" OR name:#1', "2026-13-45T00:00:00Z"])
def test_an_invalid_since_is_rejected_before_any_request(bad: str) -> None:
    fake = FakeOrders([[]])
    with pytest.raises(InvalidSince):
        reader_for(fake).recent_orders(bad)
    assert fake.requests == []


def test_boundary_order_comes_back_again_so_the_caller_dedupes_by_id() -> None:
    first = order_node(1, ["v1"])
    seen = {o.id for o in reader_for(FakeOrders([[first]])).recent_orders("2026-11-01T00:00:00Z")}
    second_poll = FakeOrders([[first, order_node(2, ["v2"])]])
    again = reader_for(second_poll).recent_orders("2026-11-01T10:00:00Z")  # from the last order
    assert "gid://shopify/Order/1" in [o.id for o in again]
    assert [o.id for o in again if o.id not in seen] == ["gid://shopify/Order/2"]
