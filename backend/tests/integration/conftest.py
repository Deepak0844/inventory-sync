"""Fixtures that run the mock Supplier on a real port and a real Chromium."""

import socket
import threading
import time
from collections.abc import Iterator

import httpx
import pytest
import uvicorn
from playwright.sync_api import Browser, sync_playwright

from app.flows.supplier_flow import SupplierFlow
from mock_supplier.app import MockState, create_mock_app


class RunningMock:
    def __init__(self, base_url: str, state: MockState) -> None:
        self.base_url = base_url
        self.state = state

    def control(self, path: str, **body: object) -> None:
        httpx.post(f"{self.base_url}/_control/{path}", json=body or None).raise_for_status()

    def outbox(self) -> list[dict[str, object]]:
        result: list[dict[str, object]] = httpx.get(f"{self.base_url}/_control/outbox").json()
        return result


@pytest.fixture
def mock_supplier() -> Iterator[RunningMock]:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    state = MockState()
    server = uvicorn.Server(
        uvicorn.Config(create_mock_app(state), port=port, log_level="warning")
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    while not server.started:
        time.sleep(0.02)
    yield RunningMock(f"http://127.0.0.1:{port}", state)
    server.should_exit = True
    thread.join(timeout=5)


@pytest.fixture(scope="session")
def browser() -> Iterator[Browser]:
    with sync_playwright() as playwright:
        chromium = playwright.chromium.launch()
        yield chromium
        chromium.close()


@pytest.fixture
def flow(mock_supplier: RunningMock) -> SupplierFlow:
    return SupplierFlow(
        base_url=mock_supplier.base_url,
        login_path="/login",
        account_path="/account",
        username_selector="input[name=username]",
        password_selector="input[name=password]",
        submit_selector="button[type=submit]",
        code_prompt_text="Enter the code",
        code_selector="input[name=code]",
        logged_in_marker='[data-testid="account-menu"]',
        blocked_text="CAPTCHA",
        stock_selector="#stock",
        in_stock_texts=("in stock",),
        out_of_stock_texts=("out of stock",),
        mail_sender="no-reply@mock-supplier.test",
        mail_code_pattern=r"code is (\d{6})",
    )
