"""Fixtures that run the mock Supplier on a real port and a real Chromium."""

import json
import socket
import threading
import time
from collections.abc import Iterator

import httpx
import pytest
import uvicorn
from playwright.sync_api import Browser, sync_playwright

from app.flows.definition import FlowDefinition
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


def mock_flow_json(base_url: str) -> str:
    """The Phase 1 mock Supplier flow, written as the JSON a Supplier would be given."""
    return json.dumps({
        "supplier": "mock-supplier",
        "version": 1,
        "login_path": "/login",
        "logged_in_url": f"{base_url}/account",
        "blocked_if": {"contains": "CAPTCHA"},
        "nodes": [
            {"id": "n1", "type": "goto", "url": f"{base_url}/login"},
            {"id": "n2", "type": "fill", "selector": "input[name=username]",
             "value": "{{credentials.username}}"},
            {"id": "n3", "type": "fill", "selector": "input[name=password]",
             "value": "{{credentials.password}}", "mask": True},
            {"id": "n4", "type": "click", "selector": "button[type=submit]"},
            {"id": "n5", "type": "wait_for", "selector": "input[name=code]",
             "role": "code_prompt", "timeout_s": 0},
            {"id": "n6", "type": "await_code", "methods": ["ui_code", "email_code"],
             "email": {"sender": "no-reply@mock-supplier.test", "pattern": "code is (\\d{6})"},
             "timeout_s": 10},
            {"id": "n7", "type": "fill", "selector": "input[name=code]", "value": "{{code}}"},
            {"id": "n8", "type": "click", "selector": "button[type=submit]"},
            {"id": "n9", "type": "wait_for", "selector": '[data-testid="account-menu"]',
             "role": "logged_in_marker", "timeout_s": 0},
            {"id": "n10", "type": "save_session"},
        ],
        "edges": [[f"n{i}", f"n{i + 1}"] for i in range(1, 10)],
        "extract": {
            "stock_selector": "#stock",
            "in_stock_if": {"contains": "in stock"},
            "out_of_stock_if": {"contains": "out of stock"},
        },
    })


@pytest.fixture
def flow(mock_supplier: RunningMock) -> FlowDefinition:
    return FlowDefinition.model_validate_json(mock_flow_json(mock_supplier.base_url))
