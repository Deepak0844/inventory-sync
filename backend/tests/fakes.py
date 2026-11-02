"""Hand-written fakes for the interfaces the app passes in (no patching)."""

from app.flows.page import PageError, PageResponse
from app.flows.supplier_flow import SupplierFlow


def sample_flow() -> SupplierFlow:
    return SupplierFlow(
        base_url="http://supplier.test", login_path="/login", account_path="/account",
        username_selector="#u", password_selector="#p", submit_selector="button",
        code_prompt_text="Enter the code", code_selector="#code",
        logged_in_marker="#me", blocked_text="CAPTCHA", stock_selector="#stock",
        in_stock_texts=("in stock",), out_of_stock_texts=("out of stock",),
        mail_sender="no-reply@supplier.test", mail_code_pattern=r"(\d{6})",
    )


class BrokenPage:
    """A page where every browser operation fails, like a timeout."""

    url = "http://supplier.test/"

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
    def __init__(self, page: BrokenPage) -> None:
        self.page = page

    def cookies_json(self) -> str:
        return "[]"

    def load_cookies_json(self, cookies_json: str) -> None:
        pass


class FakeClock:
    """A clock where `sleep` just moves time forward."""

    def __init__(self, start: float = 0.0) -> None:
        self._now = start

    def now(self) -> float:
        return self._now

    def sleep(self, seconds: float) -> None:
        self._now += seconds
