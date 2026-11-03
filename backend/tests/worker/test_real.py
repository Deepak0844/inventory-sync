import json
import time
from collections.abc import Callable
from pathlib import Path

import httpx
import pytest

from app.db.repos.jobs import JobRecord
from app.db.repos.notifications import NotificationRepo
from app.db.repos.settings import SettingsRecord, SettingsSecrets
from app.flows.page import PageError
from app.shopify.client import ShopifyError
from app.worker import real
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


def fake_chromium(tmp_path: Path) -> Path:
    """A program that records its arguments and then stays open like a browser."""
    script = tmp_path / "chromium"
    script.write_text(f'#!/bin/sh\necho "$@" > {tmp_path}/args\nexec sleep 60\n')
    script.chmod(0o755)
    return script


def test_the_plain_browser_is_an_ordinary_process_with_its_own_profile(tmp_path: Path) -> None:
    profile = tmp_path / "profile"
    with real.plain_chromium(profile, "https://s.test/login", str(fake_chromium(tmp_path))) as b:
        assert b.is_running()
        deadline = time.time() + 5
        while not (tmp_path / "args").exists() and time.time() < deadline:
            time.sleep(0.05)
        args = (tmp_path / "args").read_text()
    assert not b.is_running()
    assert f"--user-data-dir={profile}" in args and args.strip().endswith("https://s.test/login")
    # Remote control is what makes a site see "automation", so it must never be switched on.
    assert "remote-debugging" not in args and "enable-automation" not in args


def test_a_browser_that_cannot_start_is_a_page_error(tmp_path: Path) -> None:
    with pytest.raises(PageError, match="could not start"):
        with real.plain_chromium(tmp_path / "p", "https://s.test", str(tmp_path / "missing")):
            pass


def test_a_profile_without_readable_cookies_is_a_page_error_with_the_reason(
    tmp_path: Path,
) -> None:
    with pytest.raises(PageError, match="cookies") as caught:
        with real.headless_profile(tmp_path):
            pass
    assert "no cookie file" in str(caught.value.__cause__)


def test_the_plain_browser_is_closed_with_sigint_so_it_saves_its_cookies(tmp_path: Path) -> None:
    """Chromium writes cookies on SIGINT but drops recent ones on SIGTERM (checked by hand)."""
    script = tmp_path / "chromium"
    script.write_text(
        "#!/bin/sh\n"
        f"trap 'echo int > {tmp_path}/signal; exit 0' INT\n"
        f"trap 'echo term > {tmp_path}/signal; exit 0' TERM\n"
        f"echo ready > {tmp_path}/ready\n"
        "while true; do sleep 0.05; done\n"
    )
    script.chmod(0o755)
    with real.plain_chromium(tmp_path / "p", "https://s.test", str(script)):
        deadline = time.time() + 5
        while not (tmp_path / "ready").exists() and time.time() < deadline:
            time.sleep(0.05)
    assert (tmp_path / "signal").read_text().strip() == "int"


def test_the_plain_browser_keeps_session_cookies_and_stays_quiet(tmp_path: Path) -> None:
    """Logins often use cookies with no expiry; Chromium only saves those when it will restore
    the last session. Its own background requests must not put other sites' cookies in the
    saved login."""
    profile = tmp_path / "profile"
    with real.plain_chromium(profile, "https://s.test", str(fake_chromium(tmp_path))):
        deadline = time.time() + 5
        while not (tmp_path / "args").exists() and time.time() < deadline:
            time.sleep(0.05)
        args = (tmp_path / "args").read_text()
    prefs = json.loads((profile / "Default" / "Preferences").read_text())
    assert prefs["session"]["restore_on_startup"] == 1
    for flag in ("--disable-background-networking", "--disable-sync", "--disable-component-update"):
        assert flag in args
