"""Formato uniforme de errores de la API (especificación §13).

Todas las respuestas de error tienen la forma::

    {"error": {"code": "...", "message": "...", "details": {}}}

con ``message`` en español para la persona y ``code`` estable para otros
sistemas. Aquí se traducen los errores del dominio y los de validación de
FastAPI a esa forma.

No hace: no decide reglas de negocio; solo traduce errores a HTTP.
"""

from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.domain.errors import ConflictError, DomainError, InvalidRequestError, NotFoundError


class ErrorBody(BaseModel):
    """Contenido de un error."""

    code: str
    message: str
    details: dict[str, Any]


class ErrorOut(BaseModel):
    """Respuesta de error uniforme."""

    error: ErrorBody


# Para documentar en OpenAPI las respuestas de error de cada router.
ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    status.HTTP_404_NOT_FOUND: {"model": ErrorOut, "description": "No encontrado"},
    status.HTTP_409_CONFLICT: {"model": ErrorOut, "description": "Choca con algo que ya existe"},
    status.HTTP_422_UNPROCESSABLE_CONTENT: {"model": ErrorOut, "description": "Petición inválida"},
}

_HTTP_MESSAGES = {
    status.HTTP_404_NOT_FOUND: ("not_found", "La ruta no existe."),
    status.HTTP_405_METHOD_NOT_ALLOWED: ("method_not_allowed", "Método no permitido en esta ruta."),
}


def error_response(
    status_code: int, code: str, message: str, details: dict[str, Any] | None = None
) -> JSONResponse:
    """Arma una respuesta de error con el formato uniforme.

    Args:
        status_code: Código HTTP.
        code: Código estable del error.
        message: Mensaje en español.
        details: Datos adicionales.

    Returns:
        La respuesta JSON.
    """
    body = ErrorOut(error=ErrorBody(code=code, message=message, details=details or {}))
    return JSONResponse(status_code=status_code, content=body.model_dump())


def _status_for(error: DomainError) -> int:
    if isinstance(error, NotFoundError):
        return status.HTTP_404_NOT_FOUND
    if isinstance(error, ConflictError):
        return status.HTTP_409_CONFLICT
    if isinstance(error, InvalidRequestError):
        return status.HTTP_422_UNPROCESSABLE_CONTENT
    return status.HTTP_400_BAD_REQUEST


async def _domain_error(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, DomainError)  # noqa: S101 — FastAPI solo llama este manejador con DomainError
    return error_response(_status_for(exc), exc.code, exc.message, exc.details)


async def _validation_error(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)  # noqa: S101 — registrado solo para este tipo
    # Los mensajes de pydantic vienen en inglés; se entrega en español qué
    # parámetro falló y se conserva el tipo de error técnico en los detalles.
    problems = [
        {"parametro": ".".join(str(p) for p in err["loc"][1:]), "tipo": err["type"]}
        for err in exc.errors()
    ]
    names = ", ".join(p["parametro"] for p in problems) or "petición"
    return error_response(
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        "invalid_request",
        f"Parámetros inválidos o faltantes: {names}.",
        {"problemas": problems},
    )


async def _http_error(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, StarletteHTTPException)  # noqa: S101 — registrado solo para este tipo
    code, message = _HTTP_MESSAGES.get(exc.status_code, ("http_error", str(exc.detail)))
    return error_response(exc.status_code, code, message)


def register_error_handlers(app: FastAPI) -> None:
    """Registra los manejadores de error en la aplicación.

    Args:
        app: Aplicación FastAPI.
    """
    app.add_exception_handler(DomainError, _domain_error)
    app.add_exception_handler(RequestValidationError, _validation_error)
    app.add_exception_handler(StarletteHTTPException, _http_error)
