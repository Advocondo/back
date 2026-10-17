from datetime import UTC, datetime, timedelta

DEFAULT_NOW = datetime(2026, 3, 2, 9, 0, tzinfo=UTC)


class FrozenClock:
    def __init__(self, now: datetime = DEFAULT_NOW) -> None:
        self._now = now

    def now(self) -> datetime:
        return self._now

    def advance(self, duration: timedelta) -> None:
        self._now += duration
