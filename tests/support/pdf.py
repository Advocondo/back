"""Reads back the text of the PDFs the API generates.

ReportLab compresses each page (ASCII85 + Flate) and writes the text in
`(...) Tj` operators, with the accents escaped in octal (WinAnsi encoding).
"""

import base64
import re
import zlib

STREAM = re.compile(rb"stream\r?\n(.*?)endstream", re.DOTALL)
TEXT_OPERATOR = re.compile(rb"\(((?:\\.|[^\\)])*)\)\s*Tj", re.DOTALL)
ESCAPE = re.compile(rb"\\([0-7]{1,3}|.)", re.DOTALL)


def pdf_text(content: bytes) -> str:
    """The text of every page, one line per text operator."""
    lines: list[str] = []
    for stream in STREAM.findall(content):
        page = zlib.decompress(base64.a85decode(stream.strip().removesuffix(b"~>")))
        lines.extend(
            _unescape(text).decode("cp1252") for text in TEXT_OPERATOR.findall(page)
        )
    return "\n".join(lines)


def _unescape(text: bytes) -> bytes:
    def replace(match: re.Match[bytes]) -> bytes:
        escaped = match.group(1)
        if escaped.isdigit():
            return bytes([int(escaped, 8)])
        return escaped

    return ESCAPE.sub(replace, text)
