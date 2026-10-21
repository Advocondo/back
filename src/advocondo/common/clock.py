from datetime import UTC, date, datetime, timedelta, timezone
from typing import Protocol


class Clock(Protocol):
    def now(self) -> datetime: ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


def get_clock() -> Clock:
    return SystemClock()


# Horário de Brasília. O Brasil não tem horário de verão desde 2019, então um
# deslocamento fixo evita depender do banco de fusos horários do sistema.
BRAZIL_TIMEZONE = timezone(timedelta(hours=-3), "BRT")


def today_in_brazil(moment: datetime) -> date:
    """Data do calendário no Brasil no instante `moment` (que vem em UTC)."""
    return moment.astimezone(BRAZIL_TIMEZONE).date()
