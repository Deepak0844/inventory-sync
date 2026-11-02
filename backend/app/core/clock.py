"""Clock interface so time and waiting can be faked in tests.

Not responsible for scheduling; it only answers "what time is it" and "wait".
"""

import time
from typing import Protocol


class Clock(Protocol):
    """Source of the current time and of waiting."""

    def now(self) -> float:
        """Return seconds since the epoch."""
        ...

    def sleep(self, seconds: float) -> None:
        """Block for `seconds`."""
        ...


class SystemClock:
    """The real clock."""

    def now(self) -> float:
        """Return the current epoch time in seconds."""
        return time.time()

    def sleep(self, seconds: float) -> None:
        """Block the current thread for `seconds`."""
        time.sleep(seconds)
