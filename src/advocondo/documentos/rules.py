"""Regras puras dos documentos anexados a um acordo (US21)."""

from urllib.parse import unquote, urlsplit

from advocondo.documentos.errors import (
    DocumentTooLargeError,
    EmptyDocumentError,
    InvalidUrlError,
    UnsupportedDocumentTypeError,
)

MAX_DOCUMENT_SIZE = 10 * 1024 * 1024
MAX_FILENAME_LENGTH = 255
MAX_URL_LENGTH = 2048
ALLOWED_URL_SCHEMES = ("http", "https")
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


def validate_url(url: str) -> str:
    """Endereço limpo de um link. Só http e https, para o link nunca virar um script."""
    cleaned = url.strip()
    if (
        not cleaned
        or len(cleaned) > MAX_URL_LENGTH
        or any(char.isspace() or not char.isprintable() for char in cleaned)
    ):
        raise InvalidUrlError()
    try:
        parts = urlsplit(cleaned)
    except ValueError:
        raise InvalidUrlError() from None
    if parts.scheme.lower() not in ALLOWED_URL_SCHEMES or not parts.hostname:
        raise InvalidUrlError()
    return cleaned


def filename_for_link(url: str, name: str | None) -> str:
    """Nome mostrado para o link: o informado, ou o último pedaço do endereço, ou o site."""
    if name is not None and name.strip():
        return clean_filename(name)
    parts = urlsplit(url)
    last_segment = parts.path.rstrip("/").rsplit("/", 1)[-1]
    return clean_filename(unquote(last_segment) or parts.hostname)
