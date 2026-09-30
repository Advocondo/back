import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from advocondo.main import create_app
from tests.support.settings import make_settings

PRODUCAO = "https://meu-front.vercel.app"
# Mesmo formato documentado em docs/https-cors.md.
PREVIEWS = r"https://meu-front-(?:[a-z0-9]{9}|git-[a-z0-9-]+)-meu-time\.vercel\.app"


@pytest.fixture
def cors_client() -> TestClient:
    settings = make_settings(
        cors_allow_origins=[PRODUCAO],
        cors_allow_origin_regex=PREVIEWS,
    )
    return TestClient(create_app(settings))


def _preflight(client: TestClient, origin: str) -> str | None:
    response = client.options(
        "/health",
        headers={"Origin": origin, "Access-Control-Request-Method": "GET"},
    )
    allowed: str | None = response.headers.get("access-control-allow-origin")
    return allowed


@pytest.mark.parametrize(
    "origin",
    [
        pytest.param(PRODUCAO, id="producao"),
        pytest.param("https://meu-front-2f3dub5mm-meu-time.vercel.app", id="preview"),
        pytest.param(
            "https://meu-front-git-feature-login-meu-time.vercel.app",
            id="preview-de-branch",
        ),
    ],
)
def test_cors_libera_o_front(cors_client: TestClient, origin: str) -> None:
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
def test_cors_bloqueia_outras_origens(cors_client: TestClient, origin: str) -> None:
    assert _preflight(cors_client, origin) is None
    response = cors_client.get("/health", headers={"Origin": origin})
    assert "access-control-allow-origin" not in response.headers


def test_cors_fechado_por_padrao() -> None:
    client = TestClient(create_app(make_settings()))

    assert _preflight(client, PRODUCAO) is None


def test_cors_expoe_o_request_id(cors_client: TestClient) -> None:
    response = cors_client.get("/health", headers={"Origin": PRODUCAO})

    assert response.headers["access-control-expose-headers"] == "X-Request-ID"


def test_origens_separadas_por_virgula(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "CORS_ALLOW_ORIGINS", "https://a.com, https://b.com/ ,,http://localhost:3000"
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
        pytest.param("CORS_ALLOW_ORIGINS", "https://a.com,*", id="curinga-na-lista"),
        pytest.param("CORS_ALLOW_ORIGIN_REGEX", "https://(", id="regex-invalida"),
    ],
)
def test_configuracao_de_cors_invalida(
    monkeypatch: pytest.MonkeyPatch, variavel: str, valor: str
) -> None:
    monkeypatch.setenv(variavel, valor)

    with pytest.raises(ValidationError):
        make_settings()


def test_hsts_quando_configurado() -> None:
    client = TestClient(create_app(make_settings(hsts_max_age=31536000)))

    response = client.get("/health")

    assert (
        response.headers["strict-transport-security"]
        == "max-age=31536000; includeSubDomains"
    )


def test_hsts_desligado_por_padrao(client: TestClient) -> None:
    assert "strict-transport-security" not in client.get("/health").headers
