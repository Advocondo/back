"""Logging estruturado: uma linha JSON por evento, com nível e request_id."""

import json
import logging
import sys
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

# Preenchido pelo middleware de requisições; aparece em todo log da requisição.
request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)

# Atributos padrão de um LogRecord; o que não estiver aqui veio de `extra=`.
# `color_message` é a versão com cores ANSI que o uvicorn anexa às mensagens.
_RECORD_ATTRS = set(vars(logging.makeLogRecord({}))) | {
    "message",
    "asctime",
    "color_message",
}


class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if getattr(record, "request_id", None) is None:
            record.request_id = request_id_var.get()
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        entry.update(
            (key, value)
            for key, value in vars(record).items()
            if key not in _RECORD_ATTRS and value is not None
        )
        if record.exc_info:
            entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(entry, ensure_ascii=False, default=str)


CONSOLE_FORMAT = "%(asctime)s %(levelname)-8s %(name)s [%(request_id)s] %(message)s"


def configure_logging(level: str = "INFO", fmt: str = "json") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.addFilter(RequestIdFilter())
    handler.setFormatter(
        JsonFormatter() if fmt == "json" else logging.Formatter(CONSOLE_FORMAT)
    )

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)

    # Logs do uvicorn passam pelo mesmo handler. O access log dele é desligado
    # porque o middleware já registra cada requisição, com mais contexto.
    for name in ("uvicorn", "uvicorn.error", "fastapi"):
        logger = logging.getLogger(name)
        logger.handlers = []
        logger.propagate = True
    logging.getLogger("uvicorn.access").disabled = True
