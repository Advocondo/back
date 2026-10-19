"""CNPJ check digits, as defined by the Receita Federal.

Since July 2026 the CNPJ can be alphanumeric (IN RFB 2.229/2024): the first 12
characters are digits or uppercase letters and the last 2 are still numeric check
digits. The older, numeric CNPJ is a particular case and stays valid.
"""

import re

FIRST_DIGIT_WEIGHTS = (5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2)
SECOND_DIGIT_WEIGHTS = (6, *FIRST_DIGIT_WEIGHTS)
CNPJ_PATTERN = re.compile(r"^[0-9A-Z]{12}[0-9]{2}$")
MASK_CHARACTERS = re.compile(r"[\s./-]")


def normalize_cnpj(value: object) -> object:
    """Accepts masked input, such as 12.abc.345/01de-35, and returns 12ABC34501DE35."""
    if isinstance(value, str):
        return MASK_CHARACTERS.sub("", value).upper()
    return value


def is_valid_cnpj(cnpj: str) -> bool:
    """True for a normalized CNPJ whose two last digits are the right check digits."""
    if not CNPJ_PATTERN.match(cnpj) or len(set(cnpj)) == 1:
        return False
    first_check_digit = _check_digit(cnpj[:12], FIRST_DIGIT_WEIGHTS)
    second_check_digit = _check_digit(cnpj[:13], SECOND_DIGIT_WEIGHTS)
    return cnpj[12:] == f"{first_check_digit}{second_check_digit}"


def _character_value(character: str) -> int:
    """The Receita uses the ASCII code minus 48: '0'-'9' are 0-9 and 'A' is 17."""
    return ord(character) - ord("0")


def _check_digit(characters: str, weights: tuple[int, ...]) -> int:
    remainder = (
        sum(
            _character_value(character) * weight
            for character, weight in zip(characters, weights, strict=True)
        )
        % 11
    )
    return 0 if remainder < 2 else 11 - remainder
