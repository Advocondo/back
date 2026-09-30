from collections.abc import Iterator
from functools import partial
from typing import Any, ClassVar

import pytest
import sentry_sdk
from fastapi.testclient import TestClient
from sentry_sdk.envelope import Envelope
from sentry_sdk.transport import Transport

from advocondo import sentry
from advocondo.config import Settings
from advocondo.main import create_app


class CapturingTransport(Transport):
    """Guarda os eventos em memória em vez de enviá-los ao Sentry."""

    events: ClassVar[list[dict[str, Any]]] = []

    def capture_envelope(self, envelope: Envelope) -> None:
        event = envelope.get_event()
        if event is not None:
            self.events.append(dict(event))


@pytest.fixture
def sentry_events(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[dict[str, Any]]]:
    CapturingTransport.events = []
    # init_sentry chama sentry_sdk.init; injeta o transporte de teste nele.
    monkeypatch.setattr(
        sentry_sdk,
        "init",
        partial(sentry_sdk.init, transport=CapturingTransport),
    )
    yield CapturingTransport.events
    sentry_sdk.get_client().close()
    sentry_sdk.get_global_scope().set_client(None)


def test_sentry_desligado_sem_dsn() -> None:
    assert sentry.init_sentry(Settings(sentry_dsn=None)) is False


def test_erro_nao_tratado_vira_evento_no_sentry(
    sentry_events: list[dict[str, Any]],
) -> None:
    settings = Settings(
        sentry_dsn="https://chave@sentry.invalid/1",
        environment="producao",
        release="abc123",
    )
    app = create_app(settings)

    @app.get("/boom")
    def boom() -> None:
        raise RuntimeError("falha crítica")

    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/boom", headers={"X-Request-ID": "req-boom"})
    sentry_sdk.flush()

    assert response.status_code == 500
    errors = [e for e in sentry_events if e.get("exception")]
    assert errors, "nenhum evento de erro foi enviado ao Sentry"
    event = errors[0]
    assert event["exception"]["values"][-1]["type"] == "RuntimeError"
    assert event["environment"] == "producao"
    assert event["release"] == "abc123"
    assert event["tags"]["request_id"] == "req-boom"
    assert "ip_address" not in event.get("user", {})
