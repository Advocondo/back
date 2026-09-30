"""Health checks.

- /health: liveness. Só diz que o processo está de pé; não toca em dependências,
  para que uma queda do banco não faça o orquestrador reiniciar a API à toa.
- /health/ready: readiness. Verifica o banco e as demais dependências externas;
  responde 503 se alguma falhar. É o endpoint a monitorar.
"""

import logging
from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from advocondo.db import get_session

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])

HealthCheck = Callable[[], None]


def get_health_checks(
    session: Annotated[Session, Depends(get_session)],
) -> dict[str, HealthCheck]:
    """Dependências verificadas pelo /health/ready. Novas integrações entram aqui."""

    def database() -> None:
        session.execute(text("SELECT 1"))

    return {"database": database}


@router.get("/health")
def liveness() -> dict[str, str]:
    return {"status": "ok"}


@router.get(
    "/health/ready",
    responses={503: {"description": "Alguma dependência está fora do ar"}},
)
def readiness(
    checks: Annotated[dict[str, HealthCheck], Depends(get_health_checks)],
) -> JSONResponse:
    results: dict[str, str] = {}
    for name, check in checks.items():
        try:
            check()
            results[name] = "ok"
        except Exception as exc:
            # Detalhes só no log; a resposta pública não expõe o erro.
            logger.exception(
                "health check failed",
                extra={"check": name, "error": type(exc).__name__},
            )
            results[name] = "error"

    healthy = all(result == "ok" for result in results.values())
    return JSONResponse(
        status_code=200 if healthy else 503,
        content={"status": "ok" if healthy else "error", "checks": results},
    )
