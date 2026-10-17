"""When two debtors are probably the same person (US13-CA01)."""

import re
from collections.abc import Iterable

from advocondo.common.normalization import comparable_text
from advocondo.devedores.models import Debtor


def comparable_unit(unit: str) -> str:
    """'Bloco B - 304' and 'bloco b 304' are the same unit."""
    return re.sub(r"[^0-9a-z]", "", comparable_text(unit))


def find_similar_debtors(
    name: str, unit: str, candidates: Iterable[Debtor]
) -> list[Debtor]:
    """Debtors of the same condominium with the same unit or the same name.

    `candidates` are the debtors already registered in that condominium.
    """
    wanted_name = comparable_text(name)
    wanted_unit = comparable_unit(unit)
    return [
        debtor
        for debtor in candidates
        if comparable_text(debtor.name) == wanted_name
        or comparable_unit(debtor.unit) == wanted_unit
    ]
