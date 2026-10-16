"""Excepciones del dominio.

Los casos de uso las lanzan con un código estable y un mensaje en español
para el usuario. La API las traduce al formato uniforme de errores de la
especificación §13; el dominio no sabe nada de HTTP.
"""


class DomainError(Exception):
    """Error de negocio con código estable y mensaje para el usuario.

    Attributes:
        code: Identificador estable en inglés (por ejemplo ``region_not_found``),
            pensado para que otros sistemas reaccionen sin leer el mensaje.
        message: Explicación en español para la persona.
        details: Datos adicionales para diagnosticar.
    """

    code = "domain_error"

    def __init__(self, message: str, details: dict[str, object] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class NotFoundError(DomainError):
    """Lo que se pidió no existe."""

    code = "not_found"


class RegionNotFoundError(NotFoundError):
    """No existe la región pedida, o no hay ninguna región en ese punto."""

    code = "region_not_found"


class InvalidRequestError(DomainError):
    """Los datos de la petición no cumplen las reglas.

    Por ejemplo: texto de búsqueda muy corto o coordenadas fuera de rango.
    """

    code = "invalid_request"
