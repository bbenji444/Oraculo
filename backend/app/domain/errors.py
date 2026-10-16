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


class ConflictError(DomainError):
    """La petición choca con lo que ya existe (por ejemplo, un nombre repetido)."""

    code = "conflict"


class ConceptNotFoundError(NotFoundError):
    """No existe el concepto pedido (o fue borrado)."""

    code = "concept_not_found"


class ConceptNameTakenError(ConflictError):
    """Ya hay otro concepto con ese nombre (sin importar mayúsculas ni acentos)."""

    code = "concept_name_taken"


class ConceptValidationError(InvalidRequestError):
    """El concepto no cumple sus reglas.

    ``details["problemas"]`` lista cada problema con el campo al que
    pertenece, para que la interfaz lo muestre junto al campo correcto.
    """

    code = "invalid_concept"


class QueryTooLongError(InvalidRequestError):
    """La consulta no cabe en el límite del proveedor ni con una sola palabra clave.

    Pasa cuando el lugar y las exclusiones, por sí solos, ya ocupan casi
    todo el límite: repartir las palabras clave no lo arregla.
    """

    code = "query_too_long"
