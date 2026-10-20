"""Helpers for the partial-text searches of the listing routes."""


def contains_pattern(text: str) -> str:
    """LIKE pattern for `text` anywhere; typed % and _ are searched literally."""
    escaped = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


LIKE_ESCAPE_CHARACTER = "\\"
