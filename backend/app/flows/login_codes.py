"""Waiting for a Login Code from the dashboard and/or the mailbox, first one wins.

Not responsible for typing the code into the Supplier's site or for counting
failed attempts.
"""

import logging
import threading
from collections.abc import Callable, Sequence
from typing import Protocol

from app.core.clock import Clock, SystemClock
from app.mail.codes import MailboxError, MailMessage, extract_login_code

logger = logging.getLogger(__name__)


class CodeSource(Protocol):
    """Somewhere a Login Code can show up."""

    def poll(self, requested_at: float) -> str | None:
        """Return a code if one has arrived since `requested_at`, else None."""
        ...


class PastedCodeSource:
    """Codes pasted in the dashboard. Each is handed out once."""

    def __init__(self, clock: Clock | None = None) -> None:
        self._clock = clock or SystemClock()
        self._lock = threading.Lock()  # submit() runs on an API thread, poll() on the worker
        self._pasted: tuple[str, float] | None = None

    def submit(self, code: str) -> None:
        """Store a pasted code, with the time it arrived, for the waiting run."""
        with self._lock:
            self._pasted = (code, self._clock.now())

    def poll(self, requested_at: float) -> str | None:
        """Return the pasted code and forget it, so it is never reused.

        A code pasted before `requested_at` belongs to no run that is waiting
        (an earlier timeout, or pasted too early), so it is discarded rather
        than risk counting a wrong-code failed attempt.
        """
        with self._lock:
            pasted, self._pasted = self._pasted, None
        if pasted is None or pasted[1] < requested_at:
            return None
        return pasted[0]


class MailboxCodeSource:
    """Codes read from the dedicated mailbox."""

    def __init__(
        self, fetch: Callable[[], Sequence[MailMessage]], sender: str, pattern: str
    ) -> None:
        self._fetch = fetch
        self._sender = sender
        self._pattern = pattern

    def poll(self, requested_at: float) -> str | None:
        """Return a code from a new email from the Supplier's sender, if any.

        A mailbox failure is logged and treated as "no code yet", so the pasted
        path can still succeed while the mailbox is down.
        """
        try:
            messages = self._fetch()
        except MailboxError:
            logger.warning("mailbox unavailable while waiting for a Login Code", exc_info=True)
            return None
        return extract_login_code(messages, self._sender, self._pattern, requested_at)


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
