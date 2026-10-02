"""Tradução de exceções de negócio em respostas HTTP, registrada uma vez por módulo."""

from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


def register_error(
    app: FastAPI, exception: type[Exception], status_code: int, detail: Any
) -> None:
    """Responde `exception` com `status_code` e `{"detail": detail}`.

    Para erros de campo, passe `detail` no formato de validação do FastAPI
    (lista com `loc` e `msg`), para o front apontar o campo.
    """

    async def handler(_: Request, __: Exception) -> JSONResponse:
        return JSONResponse(status_code=status_code, content={"detail": detail})

    app.add_exception_handler(exception, handler)
