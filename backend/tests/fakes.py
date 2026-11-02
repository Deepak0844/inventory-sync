"""Hand-written fakes for the interfaces the app passes in (no patching)."""

from collections.abc import Callable
from typing import Any

from app.flows.definition import FlowDefinition
from app.flows.page import PageError, PageResponse


class FakeClock:
    """A clock where `sleep` just moves time forward."""

    def __init__(self, start: float = 0.0) -> None:
        self._now = start

    def now(self) -> float:
        return self._now

    def sleep(self, seconds: float) -> None:
        self._now += seconds


def sample_flow_dict() -> dict[str, Any]:
    """The PLAN.md section 11 login flow, with the extra fields Phase 2 needs."""
    return {
        "supplier": "supplier-a",
        "version": 1,
        "login_path": "/login",
        "logged_in_url": "http://supplier.test/account",
        "blocked_if": {"contains": "CAPTCHA"},
        "nodes": [
            {"id": "n1", "type": "goto", "url": "http://supplier.test/login"},
            {"id": "n2", "type": "fill", "selector": "#email",
             "value": "{{credentials.username}}"},
            {"id": "n3", "type": "fill", "selector": "#password",
             "value": "{{credentials.password}}", "mask": True},
            {"id": "n4", "type": "click", "selector": "button"},
            {"id": "n5", "type": "wait_for", "selector": "#otp", "role": "code_prompt",
             "timeout_s": 0},
            {"id": "n6", "type": "await_code", "methods": ["ui_code", "email_code"],
             "email": {"sender": "no-reply@supplier.test", "pattern": "(\\d{6})"},
             "timeout_s": 30},
            {"id": "n7", "type": "fill", "selector": "#otp", "value": "{{code}}"},
            {"id": "n8", "type": "click", "selector": "#verify"},
            {"id": "n9", "type": "wait_for", "selector": ".me", "role": "logged_in_marker",
             "timeout_s": 0},
            {"id": "n10", "type": "save_session"},
        ],
        "edges": [[f"n{i}", f"n{i + 1}"] for i in range(1, 10)],
        "extract": {
            "stock_selector": "#stock",
            "in_stock_if": {"contains": "In stock"},
            "out_of_stock_if": {"contains": "Out of stock"},
            "quantity_selector": "#qty",
        },
    }


def sample_flow() -> FlowDefinition:
    return FlowDefinition.model_validate(sample_flow_dict())


class _Response:
    def __init__(self, status: int) -> None:
        self.status = status


class ScriptedPage:
    """An in-memory page: which selectors are visible and what a click does."""

    def __init__(self, visible: set[str] | None = None, texts: dict[str, str] | None = None,
                 html: str = "", status: int = 200, url: str = "http://supplier.test/") -> None:
        self.visible = visible or set()
        self.texts = texts or {}
        self.html = html
        self.status = status
        self.url = url
        self.visited: list[str] = []
        self.filled: dict[str, str] = {}
        self.clicked: list[str] = []
        self.on_click: dict[str, Callable[[], None]] = {}

    def goto(self, url: str) -> PageResponse | None:
        self.visited.append(url)
        return _Response(self.status)

    def fill(self, selector: str, value: str) -> None:
        self.filled[selector] = value

    def click(self, selector: str) -> None:
        self.clicked.append(selector)
        if selector in self.on_click:
            self.on_click[selector]()

    def is_visible(self, selector: str) -> bool:
        return selector in self.visible

    def inner_text(self, selector: str) -> str:
        return self.texts[selector]

    def content(self) -> str:
        return self.html


class BrokenPage(ScriptedPage):
    """A page where every browser operation fails, like a timeout."""

    def goto(self, url: str) -> PageResponse | None:
        raise PageError("timeout")

    def fill(self, selector: str, value: str) -> None:
        raise PageError("timeout")

    def click(self, selector: str) -> None:
        raise PageError("timeout")

    def is_visible(self, selector: str) -> bool:
        raise PageError("timeout")

    def inner_text(self, selector: str) -> str:
        raise PageError("timeout")

    def content(self) -> str:
        raise PageError("timeout")


class FakeBrowserSession:
    def __init__(self, page: ScriptedPage) -> None:
        self.page = page
        self.loaded: str | None = None
        self.cleared = 0

    def cookies_json(self) -> str:
        return '[{"name": "session"}]'

    def load_cookies_json(self, cookies_json: str) -> None:
        self.loaded = cookies_json

    def clear_cookies(self) -> None:
        self.cleared += 1
