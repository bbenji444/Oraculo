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


class ProviderError(DomainError):
    """Un proveedor de noticias no pudo responder la consulta.

    Los adaptadores traducen a esta familia los errores HTTP y de red
    (CLAUDE.md §6.1). ``retryable`` dice si vale la pena reintentar.
    Que falle un proveedor no tumba la búsqueda: queda "parcial" (§8).

    Attributes:
        provider: Proveedor que falló (``searchapi``, ``gdelt``...).
        http_status: Código HTTP, si hubo respuesta.
    """

    code = "provider_error"
    retryable = False

    def __init__(
        self,
        message: str,
        *,
        provider: str,
        http_status: int | None = None,
        details: dict[str, object] | None = None,
    ) -> None:
        super().__init__(message, {"proveedor": provider, **(details or {})})
        self.provider = provider
        self.http_status = http_status


class ProviderNotConfiguredError(ProviderError):
    """Falta la configuración del proveedor (por ejemplo, su llave)."""

    code = "provider_not_configured"


class ProviderAuthError(ProviderError):
    """La llave fue rechazada (401/403): reintentar no sirve."""

    code = "provider_auth_error"


class ProviderRateLimitError(ProviderError):
    """El proveedor pide ir más despacio (429): se reintenta con espera."""

    code = "provider_rate_limited"
    retryable = True


class ProviderUnavailableError(ProviderError):
    """Error del servidor (5xx), red caída o tiempo agotado: se reintenta."""

    code = "provider_unavailable"
    retryable = True


class ProviderResponseError(ProviderError):
    """La respuesta no tiene el formato esperado (o es un error en texto plano)."""

    code = "provider_bad_response"


class QueryTooLongError(InvalidRequestError):
    """La consulta no cabe en el límite del proveedor ni con una sola palabra clave.

    Pasa cuando el lugar y las exclusiones, por sí solos, ya ocupan casi
    todo el límite: repartir las palabras clave no lo arregla.
    """

    code = "query_too_long"


class ServiceUnavailableError(DomainError):
    """Falta algo del sistema para atender la petición (no es culpa de quien la hace)."""

    code = "service_unavailable"


class LLMNotConfiguredError(ServiceUnavailableError):
    """La IA elegida no tiene su llave en ``.env``: no se puede buscar."""

    code = "llm_not_configured"


class CreditLimitReachedError(ConflictError):
    """La búsqueda haría pasar el tope mensual de créditos de SearchApi."""

    code = "credit_limit_reached"


class SearchNotFinishedError(ConflictError):
    """La búsqueda todavía corre: su reporte o sus datos se piden al terminar (§15)."""

    code = "search_not_finished"


class ForbiddenError(DomainError):
    """La persona no tiene permiso para esa acción (responde 403)."""

    code = "forbidden"


class CaseNotFoundError(NotFoundError):
    """No existe el caso o la persona no es miembro.

    Las dos situaciones responden igual a propósito: así no se revela que un
    caso ajeno existe (decisión D3 de la 9.3).
    """

    code = "case_not_found"


class CaseForbiddenError(ForbiddenError):
    """La persona ve el caso pero su rol no le permite esa acción."""

    code = "case_forbidden"


class CaseClosedError(ConflictError):
    """El caso está cerrado o archivado: hay que reabrirlo para cambiarlo."""

    code = "case_closed"


class CaseValidationError(InvalidRequestError):
    """El caso no cumple sus reglas (``details["problemas"]`` por campo)."""

    code = "invalid_case"
