import json
import logging
from collections.abc import Callable, Iterator
from functools import partial
from typing import Any, ClassVar

import pytest
import sentry_sdk
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sentry_sdk.envelope import Envelope
from sentry_sdk.transport import Transport
from sqlalchemy.engine import make_url

from advocondo import sentry
from advocondo.config import MIN_SETUP_TOKEN_LENGTH
from advocondo.health import HealthCheck, get_health_checks
from advocondo.logging_config import JsonFormatter, RequestIdFilter, request_id_var
from advocondo.main import app, create_app
from advocondo.middleware import resolve_request_id
from tests.support.database import assert_is_test_database
from tests.support.settings import make_settings


def _ok() -> None:
    pass


def _fail() -> None:
    raise ConnectionError("banco fora do ar")


def _format(record: logging.LogRecord) -> dict[str, object]:
    RequestIdFilter().filter(record)
    result: dict[str, object] = json.loads(JsonFormatter().format(record))
    return result


PRODUCAO = "https://meu-front.vercel.app"


# Mesmo formato documentado em docs/https-cors.md.
PREVIEWS = r"https://meu-front-(?:[a-z0-9]{9}|git-[a-z0-9-]+)-meu-time\.vercel\.app"


def _preflight(client: TestClient, origin: str) -> str | None:
    response = client.options(
        "/health",
        headers={"Origin": origin, "Access-Control-Request-Method": "GET"},
    )
    allowed: str | None = response.headers.get("access-control-allow-origin")
    return allowed


class CapturingTransport(Transport):
    """Guarda os eventos em memória em vez de enviá-los ao Sentry."""

    events: ClassVar[list[dict[str, Any]]] = []

    def capture_envelope(self, envelope: Envelope) -> None:
        event = envelope.get_event()
        if event is not None:
            self.events.append(dict(event))


BASE = "postgresql+psycopg://user:pass@localhost:5432"


class TestHealth:
    def test_liveness(self, client: TestClient) -> None:
        response = client.get("/health")

        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    @pytest.fixture
    def override_checks(self) -> Iterator[Callable[[dict[str, HealthCheck]], None]]:
        def override(checks: dict[str, HealthCheck]) -> None:
            app.dependency_overrides[get_health_checks] = lambda: checks

        yield override
        app.dependency_overrides.pop(get_health_checks, None)

    @pytest.mark.parametrize(
        ("checks", "status_code", "expected"),
        [
            pytest.param(
                {"database": _ok},
                200,
                {"status": "ok", "checks": {"database": "ok"}},
                id="tudo-ok",
            ),
            pytest.param(
                {"database": _fail},
                503,
                {"status": "error", "checks": {"database": "error"}},
                id="banco-fora",
            ),
            pytest.param(
                {"database": _ok, "email": _fail},
                503,
                {"status": "error", "checks": {"database": "ok", "email": "error"}},
                id="dependencia-externa-fora",
            ),
        ],
    )
    def test_readiness(
        self,
        client: TestClient,
        override_checks: Callable[[dict[str, HealthCheck]], None],
        checks: dict[str, HealthCheck],
        status_code: int,
        expected: dict[str, object],
    ) -> None:
        override_checks(checks)

        response = client.get("/health/ready")

        assert response.status_code == status_code
        assert response.json() == expected

    def test_readiness_nao_expoe_o_erro(
        self,
        client: TestClient,
        override_checks: Callable[[dict[str, HealthCheck]], None],
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        override_checks({"database": _fail})

        response = client.get("/health/ready")

        assert "fora do ar" not in response.text
        [record] = [
            r for r in caplog.records if r.getMessage() == "health check failed"
        ]
        assert record.levelname == "ERROR"
        assert record.__dict__["check"] == "database"


class TestLogging:
    def test_json_formatter_gera_campos_padrao_e_extras(self) -> None:
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

    def test_json_formatter_descarta_color_message_do_uvicorn(self) -> None:
        record = logging.makeLogRecord(
            {"msg": "Started server process", "color_message": "\x1b[36mStarted\x1b[0m"}
        )

        assert "color_message" not in _format(record)

    def test_json_formatter_inclui_request_id_do_contexto(self) -> None:
        token = request_id_var.set("abc123")
        try:
            entry = _format(logging.makeLogRecord({"msg": "dentro da requisição"}))
        finally:
            request_id_var.reset(token)

        assert entry["request_id"] == "abc123"

    def test_json_formatter_inclui_exception(self) -> None:
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
    def test_resolve_request_id(self, header: str | None, mantido: bool) -> None:
        request_id = resolve_request_id(header)

        assert (request_id == header) is mantido
        assert request_id

    def test_middleware_registra_requisicao_e_devolve_request_id(
        self, client: TestClient, caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level(logging.DEBUG, logger="advocondo.requests"):
            response = client.get("/health", headers={"X-Request-ID": "teste-1"})

        assert response.headers["X-Request-ID"] == "teste-1"
        [record] = [r for r in caplog.records if r.name == "advocondo.requests"]
        assert record.levelno == logging.DEBUG  # health check não polui o INFO
        assert record.__dict__["request_id"] == "teste-1"
        assert record.__dict__["status_code"] == 200
        assert record.__dict__["path"] == "/health"


class TestSecurity:
    @pytest.fixture
    def cors_client(self) -> TestClient:
        settings = make_settings(
            cors_allow_origins=[PRODUCAO],
            cors_allow_origin_regex=PREVIEWS,
        )
        return TestClient(create_app(settings))

    @pytest.mark.parametrize(
        "origin",
        [
            pytest.param(PRODUCAO, id="producao"),
            pytest.param(
                "https://meu-front-2f3dub5mm-meu-time.vercel.app", id="preview"
            ),
            pytest.param(
                "https://meu-front-git-feature-login-meu-time.vercel.app",
                id="preview-de-branch",
            ),
        ],
    )
    def test_cors_libera_o_front(self, cors_client: TestClient, origin: str) -> None:
        assert _preflight(cors_client, origin) == origin
        response = cors_client.get("/health", headers={"Origin": origin})
        assert response.headers["access-control-allow-origin"] == origin

    @pytest.mark.parametrize(
        "origin",
        [
            pytest.param("https://site-qualquer.com", id="outro-dominio"),
            pytest.param("http://meu-front.vercel.app", id="http-sem-tls"),
            pytest.param("https://outro-front.vercel.app", id="outro-projeto-vercel"),
            pytest.param(
                "https://meu-front-2f3dub5mm-outro-time.vercel.app",
                id="preview-de-outro-time",
            ),
            pytest.param(
                "https://meu-front-2f3dub5mm-meu-time.vercel.app.evil.com",
                id="sufixo-malicioso",
            ),
            pytest.param(
                "https://evil.com/https://meu-front.vercel.app", id="prefixo-malicioso"
            ),
            pytest.param("null", id="origem-null"),
        ],
    )
    def test_cors_bloqueia_outras_origens(
        self, cors_client: TestClient, origin: str
    ) -> None:
        assert _preflight(cors_client, origin) is None
        response = cors_client.get("/health", headers={"Origin": origin})
        assert "access-control-allow-origin" not in response.headers

    def test_cors_fechado_por_padrao(self) -> None:
        client = TestClient(create_app(make_settings()))

        assert _preflight(client, PRODUCAO) is None

    def test_cors_expoe_o_request_id(self, cors_client: TestClient) -> None:
        response = cors_client.get("/health", headers={"Origin": PRODUCAO})

        assert response.headers["access-control-expose-headers"] == "X-Request-ID"

    def test_origens_separadas_por_virgula(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(
            "CORS_ALLOW_ORIGINS",
            "https://a.com, https://b.com/ ,,http://localhost:3000",
        )

        settings = make_settings()

        assert settings.cors_allow_origins == [
            "https://a.com",
            "https://b.com",
            "http://localhost:3000",
        ]

    @pytest.mark.parametrize(
        ("variavel", "valor"),
        [
            pytest.param("CORS_ALLOW_ORIGINS", "*", id="curinga"),
            pytest.param(
                "CORS_ALLOW_ORIGINS", "https://a.com,*", id="curinga-na-lista"
            ),
            pytest.param("CORS_ALLOW_ORIGIN_REGEX", "https://(", id="regex-invalida"),
        ],
    )
    def test_configuracao_de_cors_invalida(
        self, monkeypatch: pytest.MonkeyPatch, variavel: str, valor: str
    ) -> None:
        monkeypatch.setenv(variavel, valor)

        with pytest.raises(ValidationError):
            make_settings()

    def test_hsts_quando_configurado(self) -> None:
        client = TestClient(create_app(make_settings(hsts_max_age=31536000)))

        response = client.get("/health")

        assert (
            response.headers["strict-transport-security"]
            == "max-age=31536000; includeSubDomains"
        )

    def test_hsts_desligado_por_padrao(self, client: TestClient) -> None:
        assert "strict-transport-security" not in client.get("/health").headers


class TestConfig:
    @pytest.mark.parametrize(
        ("setup_token", "expected"),
        [
            pytest.param("", None, id="empty-disables-setup"),
            pytest.param(
                "a" * MIN_SETUP_TOKEN_LENGTH,
                "a" * MIN_SETUP_TOKEN_LENGTH,
                id="minimum-length",
            ),
        ],
    )
    def test_setup_token_accepts_empty_or_long_enough_values(
        self, setup_token: str, expected: str | None
    ) -> None:
        assert make_settings(setup_token=setup_token).setup_token == expected

    def test_setup_token_shorter_than_the_minimum_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="SETUP_TOKEN"):
            make_settings(setup_token="a" * (MIN_SETUP_TOKEN_LENGTH - 1))


class TestSentry:
    @pytest.fixture
    def sentry_events(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> Iterator[list[dict[str, Any]]]:
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

    def test_sentry_desligado_sem_dsn(self) -> None:
        assert sentry.init_sentry(make_settings()) is False

    def test_erro_nao_tratado_vira_evento_no_sentry(
        self,
        sentry_events: list[dict[str, Any]],
    ) -> None:
        settings = make_settings(
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


class TestDatabaseGuard:
    @pytest.mark.parametrize(
        "database",
        ["advocondo_test", "outro_test"],
    )
    def test_aceita_banco_de_testes(self, database: str) -> None:
        assert_is_test_database(make_url(f"{BASE}/{database}"))

    @pytest.mark.parametrize(
        "database",
        [
            pytest.param("advocondo", id="banco-de-dev"),
            pytest.param("advocondo_prod", id="banco-de-producao"),
            pytest.param("test_advocondo", id="test-no-inicio"),
            pytest.param("", id="sem-nome"),
        ],
    )
    def test_recusa_banco_que_nao_e_de_testes(self, database: str) -> None:
        with pytest.raises(ValueError, match="_test"):
            assert_is_test_database(make_url(f"{BASE}/{database}"))
