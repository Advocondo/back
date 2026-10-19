from datetime import date
from typing import Annotated

from fastapi import Depends

from advocondo.common.clock import Clock, get_clock, today_in_brazil


def get_today(clock: Annotated[Clock, Depends(get_clock)]) -> date:
    """Data de hoje no Brasil, para comparar com datas de vencimento."""
    return today_in_brazil(clock.now())


Today = Annotated[date, Depends(get_today)]