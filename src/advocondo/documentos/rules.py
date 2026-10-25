"""Regras puras dos documentos anexados a um acordo (US21)."""

from advocondo.documentos.errors import (
    DocumentTooLargeError,
    EmptyDocumentError,
    UnsupportedDocumentTypeError,
)

MAX_DOCUMENT_SIZE = 10 * 1024 * 1024
MAX_FILENAME_LENGTH = 255
DEFAULT_FILENAME = "documento"

# Começo do conteúdo de cada tipo aceito.
SIGNATURES = (
    (b"%PDF-", "application/pdf"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
)


def detect_content_type(content: bytes) -> str | None:
    """Tipo do arquivo pelo conteúdo, e não pelo que o cliente diz. None se não é aceito."""
    for signature, content_type in SIGNATURES:
        if content.startswith(signature):
            return content_type
    return None


def clean_filename(filename: str | None) -> str:
    """Só o nome do arquivo: sem pastas, sem caracteres de controle e com até 255 caracteres."""
    name = (filename or "").replace("\\", "/").rsplit("/", 1)[-1]
    name = "".join(char for char in name if char.isprintable()).strip()
    if name in ("", ".", ".."):
        return DEFAULT_FILENAME
    return name[:MAX_FILENAME_LENGTH]


def validate_document(content: bytes) -> str:
    """Confere o arquivo e devolve o tipo detectado."""
    if not content:
        raise EmptyDocumentError()
    if len(content) > MAX_DOCUMENT_SIZE:
        raise DocumentTooLargeError()
    content_type = detect_content_type(content)
    if content_type is None:
        raise UnsupportedDocumentTypeError()
    return content_type
