"""CORS e cabeçalhos de segurança HTTP. Ver docs/https-cors.md."""

from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from advocondo.config import Settings


def configure_cors(app: FastAPI, settings: Settings) -> None:
    """Libera só as origens configuradas: o front em produção e, por regex, os
    previews da Vercel. Qualquer outra origem não recebe cabeçalhos CORS, e o
    navegador bloqueia a resposta."""
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allow_origins,
        allow_origin_regex=settings.cors_allow_origin_regex,
        allow_credentials=settings.cors_allow_credentials,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
        expose_headers=["X-Request-ID"],
        max_age=600,
    )


def hsts_middleware(
    max_age: int,
) -> Callable[[Request, Callable[[Request], Awaitable[Response]]], Awaitable[Response]]:
    """Diz ao navegador para usar só HTTPS com a API pelos próximos `max_age` s.

    O redirecionamento HTTP → HTTPS e o certificado ficam no proxy do Coolify;
    este cabeçalho impede que o navegador volte a tentar HTTP depois disso.
    """
    value = f"max-age={max_age}; includeSubDomains"

    async def middleware(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        response = await call_next(request)
        response.headers["Strict-Transport-Security"] = value
        return response

    return middleware
