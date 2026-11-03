"""Plain data returned by flow runs.

Not responsible for producing these values; `app.flows.runner` does.
"""

from dataclasses import dataclass, field
from enum import Enum


@dataclass(frozen=True)
class Credentials:
    """A Supplier account. The password is kept out of reprs and logs."""

    username: str
    password: str = field(repr=False)


class LoginResult(Enum):
    """How a login run ended.

    Only WRONG_CODE and BAD_CREDENTIALS count as failed attempts.
    """

    SESSION_REUSED = "session_reused"
    LOGGED_IN = "logged_in"
    WRONG_CODE = "wrong_code"
    BAD_CREDENTIALS = "bad_credentials"
    CODE_TIMEOUT = "code_timeout"
    BLOCKED = "blocked"
    BROWSER_ERROR = "browser_error"
    FLOW_FAILURE = "flow_failure"


class ReadingResult(Enum):
    """Outcome of reading one Listing."""

    IN_STOCK = "in_stock"
    OUT_OF_STOCK = "out_of_stock"
    LISTING_REMOVED = "listing_removed"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class Reading:
    """One reading. `error_kind` explains an UNKNOWN result."""

    result: ReadingResult
    error_kind: str | None = None
    quantity: int | None = None
    # Which extract rule matched ("in_stock_if" or "out_of_stock_if"); shown by Test runs.
    matched_rule: str | None = None
