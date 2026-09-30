import json
import logging

import pytest
from fastapi.testclient import TestClient

from advocondo.logging_config import JsonFormatter, RequestIdFilter, request_id_var
from advocondo.middleware import resolve_request_id


def _format(record: logging.LogRecord) -> dict[str, object]:
    RequestIdFilter().filter(record)
    result: dict[str, object] = json.loads(JsonFormatter().format(record))
    return result


def test_json_formatter_gera_campos_padrao_e_extras() -> None:
    record = logging.makeLogRecord(
        {
            "name": "advocondo.teste",
            "levelname": "WARNING",
            "msg": "olá %s",
            "args": ("mundo",),
            "acordo_id": 42,
        }
    )

    entry = _format(record)

    assert entry["level"] == "WARNING"
    assert entry["logger"] == "advocondo.teste"
    assert entry["message"] == "olá mundo"
    assert entry["acordo_id"] == 42
    assert "timestamp" in entry


def test_json_formatter_descarta_color_message_do_uvicorn() -> None:
    record = logging.makeLogRecord(
        {"msg": "Started server process", "color_message": "\x1b[36mStarted\x1b[0m"}
    )

    assert "color_message" not in _format(record)


def test_json_formatter_inclui_request_id_do_contexto() -> None:
    token = request_id_var.set("abc123")
    try:
        entry = _format(logging.makeLogRecord({"msg": "dentro da requisição"}))
    finally:
        request_id_var.reset(token)

    assert entry["request_id"] == "abc123"


def test_json_formatter_inclui_exception() -> None:
    try:
        raise ValueError("falhou")
    except ValueError:
        record = logging.makeLogRecord({"msg": "erro", "exc_info": True})
        record.exc_info = __import__("sys").exc_info()

    entry = _format(record)

    assert "ValueError: falhou" in str(entry["exception"])


@pytest.mark.parametrize(
    ("header", "mantido"),
    [
        pytest.param("req-123.abc_DEF", True, id="valido"),
        pytest.param(None, False, id="ausente"),
        pytest.param("", False, id="vazio"),
        pytest.param("tem espaço", False, id="caractere-invalido"),
        pytest.param("x" * 65, False, id="longo-demais"),
    ],
)
def test_resolve_request_id(header: str | None, mantido: bool) -> None:
    request_id = resolve_request_id(header)

    assert (request_id == header) is mantido
    assert request_id


def test_middleware_registra_requisicao_e_devolve_request_id(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.DEBUG, logger="advocondo.requests"):
        response = client.get("/health", headers={"X-Request-ID": "teste-1"})

    assert response.headers["X-Request-ID"] == "teste-1"
    [record] = [r for r in caplog.records if r.name == "advocondo.requests"]
    assert record.levelno == logging.DEBUG  # health check não polui o INFO
    assert record.__dict__["request_id"] == "teste-1"
    assert record.__dict__["status_code"] == 200
    assert record.__dict__["path"] == "/health"
