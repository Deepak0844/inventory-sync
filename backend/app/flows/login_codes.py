"""Waiting for a Login Code from the dashboard and/or the mailbox, first one wins.

Not responsible for typing the code into the Supplier's site or for counting
failed attempts.
"""

from collections.abc import Callable, Sequence
from typing import Protocol

from app.core.clock import Clock
from app.mail.codes import MailMessage, extract_login_code


class CodeSource(Protocol):
    """Somewhere a Login Code can show up."""

    def poll(self, requested_at: float) -> str | None:
        """Return a code if one has arrived since `requested_at`, else None."""
        ...


class PastedCodeSource:
    """Codes pasted in the dashboard. Each is handed out once."""

    def __init__(self) -> None:
        self._code: str | None = None

    def submit(self, code: str) -> None:
        """Store a pasted code for the waiting run."""
        self._code = code

    def poll(self, requested_at: float) -> str | None:
        """Return the pasted code and forget it, so it is never reused."""
        code, self._code = self._code, None
        return code


class MailboxCodeSource:
    """Codes read from the dedicated mailbox."""

    def __init__(
        self, fetch: Callable[[], Sequence[MailMessage]], sender: str, pattern: str
    ) -> None:
        self._fetch = fetch
        self._sender = sender
        self._pattern = pattern

    def poll(self, requested_at: float) -> str | None:
        """Return a code from a new email from the Supplier's sender, if any."""
        return extract_login_code(self._fetch(), self._sender, self._pattern, requested_at)


def await_login_code(
    sources: Sequence[CodeSource],
    clock: Clock,
    requested_at: float,
    timeout: float,
    interval: float,
) -> str | None:
    """Poll every source until one yields a code or `timeout` seconds pass.

    The first source to produce a code wins and the rest are not consulted
    again. Returns None on timeout; the caller cancels the run without counting
    a failed attempt.
    """
    deadline = clock.now() + timeout
    while True:
        for source in sources:
            code = source.poll(requested_at)
            if code is not None:
                return code
        if clock.now() >= deadline:
            return None
        clock.sleep(interval)
