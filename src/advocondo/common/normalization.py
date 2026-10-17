"""Text normalization shared by request schemas and comparison rules."""

import re
import unicodedata


def keep_only_digits(value: object) -> object:
    """Accepts masked input, such as 14.447.918/0001-98 or (61) 91234-5678."""
    if isinstance(value, str):
        return re.sub(r"\D", "", value)
    return value


def comparable_text(text: str) -> str:
    """Lowercase, without accents and with single spaces: 'José  Simão' -> 'jose simao'."""
    without_accents = "".join(
        character
        for character in unicodedata.normalize("NFKD", text)
        if not unicodedata.combining(character)
    )
    return " ".join(without_accents.casefold().split())
