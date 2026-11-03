import json

import httpx
import pytest

from app.shopify.auth import ClientCredentialsToken
from app.shopify.client import ShopifyClient, ShopifyError
from app.shopify.variants import ShopifyVariantReader, ShopVariant
from tests.fakes import FakeClock


def token_source(handler: httpx.MockTransport | None = None, clock: FakeClock | None = None,
                 calls: list[httpx.Request] | None = None) -> ClientCredentialsToken:
    def respond(request: httpx.Request) -> httpx.Response:
        if calls is not None:
            calls.append(request)
        return httpx.Response(200, json={"access_token": f"tok{len(calls or [])}",
                                         "expires_in": 86399})

    return ClientCredentialsToken("s.myshopify.com", "cid", "csecret",
                                  handler or httpx.MockTransport(respond), clock or FakeClock())


def test_token_is_requested_with_the_client_credentials_grant() -> None:
    calls: list[httpx.Request] = []
    assert token_source(calls=calls).token() == "tok1"
    body = json.loads(calls[0].content)
    assert body == {"client_id": "cid", "client_secret": "csecret",
                    "grant_type": "client_credentials"}
    assert str(calls[0].url) == "https://s.myshopify.com/admin/oauth/access_token"


def test_token_is_reused_until_shortly_before_it_expires() -> None:
    calls: list[httpx.Request] = []
    clock = FakeClock()
    source = token_source(clock=clock, calls=calls)
    source.token()
    clock.sleep(86399 - 120)
    assert source.token() == "tok1"
    clock.sleep(100)  # inside the 60 s safety margin of expiry
    assert source.token() == "tok2"


def test_a_rejected_token_request_raises_without_leaking_the_secret() -> None:
    source = token_source(httpx.MockTransport(lambda r: httpx.Response(401, text="csecret bad")))
    with pytest.raises(ShopifyError) as error:
        source.token()
    assert "csecret" not in str(error.value)


def variants_client(pages: list[dict[str, object]]) -> ShopifyClient:
    queue = list(pages)

    def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": {"productVariants": queue.pop(0)}})

    return ShopifyClient("s.myshopify.com", "t", httpx.MockTransport(respond), FakeClock())


def node(i: int, sku: str | None) -> dict[str, object]:
    return {"id": f"gid://shopify/ProductVariant/{i}", "sku": sku, "displayName": f"Shirt - {i}"}


def test_variants_are_read_across_pages() -> None:
    client = variants_client([
        {"nodes": [node(1, "A")], "pageInfo": {"hasNextPage": True, "endCursor": "c1"}},
        {"nodes": [node(2, "B")], "pageInfo": {"hasNextPage": False, "endCursor": None}},
    ])
    assert ShopifyVariantReader(client).all_variants() == [
        ShopVariant("gid://shopify/ProductVariant/1", "A", "Shirt - 1"),
        ShopVariant("gid://shopify/ProductVariant/2", "B", "Shirt - 2"),
    ]


def test_variants_without_a_sku_are_skipped() -> None:
    client = variants_client([{"nodes": [node(1, None), node(2, ""), node(3, "C")],
                               "pageInfo": {"hasNextPage": False, "endCursor": None}}])
    assert [v.sku for v in ShopifyVariantReader(client).all_variants()] == ["C"]
