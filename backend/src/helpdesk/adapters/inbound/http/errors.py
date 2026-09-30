"""Traducción de errores del dominio a respuestas HTTP con un formato uniforme."""

from collections.abc import Mapping
from typing import Any

import structlog
from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from helpdesk.domain.errors import (
    AuthenticationError,
    ConflictError,
    DomainError,
    InvalidTransitionError,
    NotFoundError,
    PermissionDeniedError,
    TabConflictError,
    TooManyAttemptsError,
    ValidationError,
)

log = structlog.get_logger("helpdesk.errors")

STATUS_BY_ERROR: dict[type[DomainError], int] = {
    NotFoundError: status.HTTP_404_NOT_FOUND,
    PermissionDeniedError: status.HTTP_403_FORBIDDEN,
    ConflictError: status.HTTP_409_CONFLICT,
    InvalidTransitionError: status.HTTP_409_CONFLICT,
    TabConflictError: status.HTTP_409_CONFLICT,
    ValidationError: status.HTTP_422_UNPROCESSABLE_CONTENT,
    AuthenticationError: status.HTTP_401_UNAUTHORIZED,
    TooManyAttemptsError: status.HTTP_429_TOO_MANY_REQUESTS,
}


def error_response(
    status_code: int,
    code: str,
    message: str,
    details: list[dict[str, Any]] | None = None,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    body: dict[str, Any] = {"error": {"code": code, "message": message}}
    if details is not None:
        body["error"]["details"] = details
    return JSONResponse(jsonable_encoder(body), status_code=status_code, headers=headers)


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(DomainError)
    async def domain_error(_: Request, exc: DomainError) -> JSONResponse:
        code = next(
            (c for t, c in STATUS_BY_ERROR.items() if isinstance(exc, t)),
            status.HTTP_400_BAD_REQUEST,
        )
        headers = {"WWW-Authenticate": "Bearer"} if code == 401 else None
        if code >= 500 or isinstance(exc, (PermissionDeniedError, TabConflictError)):
            log.warning("domain_error", code=exc.code, message=exc.message)
        return error_response(code, exc.code, exc.message, headers=headers)

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        details = [
            {"loc": list(e.get("loc", ())), "msg": e.get("msg"), "type": e.get("type")}
            for e in exc.errors()
        ]
        return error_response(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "validation_error",
            "Los datos enviados no son válidos.",
            details,
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        return error_response(exc.status_code, "http_error", str(exc.detail), headers=exc.headers)

    @app.exception_handler(Exception)
    async def unhandled(_: Request, exc: Exception) -> JSONResponse:
        log.exception("unhandled_error", error=type(exc).__name__)
        return error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "internal_error",
            "Ocurrió un error inesperado. Intenta de nuevo.",
        )
