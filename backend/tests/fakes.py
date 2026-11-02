"""Hand-written fakes for the interfaces the app passes in (no patching)."""


class FakeClock:
    """A clock where `sleep` just moves time forward."""

    def __init__(self, start: float = 0.0) -> None:
        self._now = start

    def now(self) -> float:
        return self._now

    def sleep(self, seconds: float) -> None:
        self._now += seconds
