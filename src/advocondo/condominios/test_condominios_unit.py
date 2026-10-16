from datetime import date, timedelta

import pytest

from advocondo.condominios.renewal import DEFAULT_RENEWAL_WARNING_DAYS, is_near_renewal

TODAY = date(2026, 10, 15)


class TestIsNearRenewal:
    @pytest.mark.parametrize(
        ("days_until_renewal", "expected"),
        [
            pytest.param(365, False, id="renewal-in-a-year"),
            pytest.param(
                DEFAULT_RENEWAL_WARNING_DAYS + 1, False, id="one-day-outside-the-window"
            ),
            pytest.param(
                DEFAULT_RENEWAL_WARNING_DAYS, True, id="last-day-of-the-window"
            ),
            pytest.param(5, True, id="renewal-in-a-few-days"),
            pytest.param(0, True, id="renewal-today"),
            pytest.param(-1, True, id="renewal-date-already-passed"),
        ],
    )
    def test_contract_is_flagged_inside_the_default_window(
        self, days_until_renewal: int, expected: bool
    ) -> None:
        """US23-CA01"""
        renewal_date = TODAY + timedelta(days=days_until_renewal)

        assert is_near_renewal(renewal_date, today=TODAY) is expected