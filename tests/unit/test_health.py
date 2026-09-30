from collections.abc import Callable, Iterator

import pytest
from fastapi.testclient import TestClient

from advocondo.health import HealthCheck, get_health_checks
from advocondo.main import app


def test_liveness(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def _ok() -> None:
    pass


def _fail() -> None:
    raise ConnectionError("banco fora do ar")


@pytest.fixture
def override_checks() -> Iterator[Callable[[dict[str, HealthCheck]], None]]:
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
    client: TestClient,
    override_checks: Callable[[dict[str, HealthCheck]], None],
    caplog: pytest.LogCaptureFixture,
) -> None:
    override_checks({"database": _fail})

    response = client.get("/health/ready")

    assert "fora do ar" not in response.text
    [record] = [r for r in caplog.records if r.getMessage() == "health check failed"]
    assert record.levelname == "ERROR"
    assert record.__dict__["check"] == "database"
