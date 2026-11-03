from collections.abc import Callable

import httpx

from app.db.repos.jobs import JobRecord
from app.db.repos.notifications import NotificationRepo
from app.db.repos.settings import SettingsRecord, SettingsSecrets
from app.shopify.client import ShopifyError
from app.worker.real import RealShopifyFactory, imap_fetch
from app.worker.sync import handle_sync_variants
from tests.fakes import FakeClock
from tests.worker.conftest import World


def settings(shop: str = "s.myshopify.com", client_id: str = "cid") -> SettingsRecord:
    return SettingsRecord(shop, client_id, True, "imap.test", "box@test", True, 0.3, 20, 6, 5)


def test_shopify_is_not_available_until_the_shop_and_app_are_set_up() -> None:
    factory = RealShopifyFactory(FakeClock(), lambda: httpx.MockTransport(lambda r: None))  # type: ignore[arg-type]
    assert factory(settings(shop=""), SettingsSecrets("secret", None)) is None
    assert factory(settings(client_id=""), SettingsSecrets("secret", None)) is None
    assert factory(settings(), SettingsSecrets(None, None)) is None


def test_the_token_comes_from_client_credentials_and_is_reused_across_jobs() -> None:
    seen: list[tuple[str, str | None]] = []

    def respond(request: httpx.Request) -> httpx.Response:
        seen.append((request.url.path, request.headers.get("X-Shopify-Access-Token")))
        if request.url.path.endswith("/oauth/access_token"):
            return httpx.Response(200, json={"access_token": "tok", "expires_in": 86399})
        return httpx.Response(200, json={"data": {"productVariants": {
            "nodes": [], "pageInfo": {"hasNextPage": False, "endCursor": None}}}})

    factory = RealShopifyFactory(FakeClock(), lambda: httpx.MockTransport(respond))
    for _ in range(2):
        api = factory(settings(), SettingsSecrets("secret", None))
        assert api is not None
        api.all_variants()
    tokens = [p for p, _ in seen if p.endswith("/oauth/access_token")]
    assert len(tokens) == 1
    assert all(h == "tok" for p, h in seen if "graphql" in p)


def test_a_refused_token_is_reported_to_the_owner_not_raised_from_the_job(
    make_world: Callable[..., World],
) -> None:
    w = make_world(variants=1)

    def refuse(settings: SettingsRecord, secrets: SettingsSecrets) -> None:
        raise ShopifyError("Shopify refused the token request (401)")

    w.deps.shopify = refuse
    with w.deps.session_factory() as s:
        handle_sync_variants(w.deps, s, JobRecord(1, "sync_variants", None, {}, 0))
    assert [n.kind for n in NotificationRepo(w.session).list(resolved=False)] == ["shopify_error"]


def test_the_mailbox_is_only_available_with_all_three_settings() -> None:
    assert imap_fetch(settings(), SettingsSecrets(None, "pw")) is not None
    assert imap_fetch(settings(), SettingsSecrets(None, None)) is None
    no_host = SettingsRecord("s", "c", True, "", "u", True, 0.3, 20, 6, 5)
    assert imap_fetch(no_host, SettingsSecrets(None, "pw")) is None


