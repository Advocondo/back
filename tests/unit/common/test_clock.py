from datetime import UTC

from advocondo.common.clock import get_clock


def test_system_clock_returns_an_aware_utc_datetime() -> None:
    assert get_clock().now().tzinfo == UTC
