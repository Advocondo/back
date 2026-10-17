from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from advocondo.common.errors import (
    AppError,
    AuthenticationError,
    BusinessRuleError,
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
)

STATUS_BY_ERROR: dict[type[AppError], int] = {
    AuthenticationError: status.HTTP_401_UNAUTHORIZED,
    PermissionDeniedError: status.HTTP_403_FORBIDDEN,
    NotFoundError: status.HTTP_404_NOT_FOUND,
    ConflictError: status.HTTP_409_CONFLICT,
    BusinessRuleError: status.HTTP_422_UNPROCESSABLE_CONTENT,
}


def status_for(error: AppError) -> int:
    for error_class in type(error).__mro__:
        if error_class in STATUS_BY_ERROR:
            return STATUS_BY_ERROR[error_class]
    return status.HTTP_400_BAD_REQUEST


async def handle_app_error(request: Request, error: Exception) -> JSONResponse:
    assert isinstance(error, AppError)
    headers = (
        {"WWW-Authenticate": "Bearer"}
        if isinstance(error, AuthenticationError)
        else None
    )
    return JSONResponse(
        {"detail": error.message}, status_code=status_for(error), headers=headers
    )


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, handle_app_error)
