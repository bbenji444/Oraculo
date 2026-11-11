"""Reglas de una búsqueda completa (especificación §9).

- **Estado final:** ``completed`` si todo salió; ``partial`` si alguna etapa
  falló en más de la mitad de las notas o algún proveedor falló;
  ``failed`` si no se pudo consultar a ningún proveedor.
- **Dentro de la región:** una nota está dentro si su ubicación principal
  cae en la región buscada (por el prefijo de la clave INEGI, §6). Las de
  fuera **no se borran**: se muestran aparte.

No hace: no consulta nada ni guarda (eso es el caso de uso del pipeline).
"""

from dataclasses import dataclass
from enum import StrEnum

from app.domain.geocoding import Place
from app.domain.region import RegionLevel

# §9: "Si más del 50% de las noticias falla en una etapa, la búsqueda queda
# en partial".
MAX_FAILED_SHARE = 0.5


class SearchStatus(StrEnum):
    """Columna ``searches.status``."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"

    @property
    def is_finished(self) -> bool:
        """Si ya no va a cambiar (bien, a medias o con falla): tiene reporte."""
        return self in (SearchStatus.COMPLETED, SearchStatus.PARTIAL, SearchStatus.FAILED)


class SearchTrigger(StrEnum):
    """Columna ``searches.trigger``: quién lanzó la búsqueda (F12.8, ADR-0031)."""

    MANUAL = "manual"
    """Una persona, desde Explorar o con ``make buscar``."""
    AUTOMATIC = "automatic"
    """El reloj, en un horario fijo del monitor FGR (07:00, 15:00, 23:00)."""


def can_delete_search(owner_id: str, trigger: SearchTrigger, user_id: str) -> bool:
    """Si una persona puede quitar una búsqueda del historial.

    Las suyas sí. Las corridas automáticas del monitor FGR son de todos y salen
    en el historial de todos (ADR-0031), así que cualquiera puede quitarlas.
    Las búsquedas manuales de otra persona, no.

    Args:
        owner_id: Quién la lanzó (``searches.user_id``).
        trigger: Manual o automática.
        user_id: Quién quiere eliminarla.

    Returns:
        ``True`` si puede.
    """
    return trigger is SearchTrigger.AUTOMATIC or owner_id == user_id


class Stage(StrEnum):
    """Etapas del pipeline (§9), para ``progress`` y ``processing_errors``."""

    PLAN = "plan"
    QUERY = "query"
    DEDUPE = "dedupe"
    EXTRACT = "extract"
    ENRICH = "enrich"
    GEOCODE = "geocode"
    FILTER = "filter"
    CLOSE = "close"


@dataclass(frozen=True, slots=True)
class StageCount:
    """Cuántas notas pasaron y cuántas fallaron en una etapa.

    Attributes:
        stage: Etapa.
        total: Notas que entraron.
        failed: Notas que fallaron.
    """

    stage: Stage
    total: int
    failed: int

    @property
    def failed_too_much(self) -> bool:
        """``True`` si falló más de la mitad (§9)."""
        return self.total > 0 and self.failed / self.total > MAX_FAILED_SHARE


def final_status(
    queries_ok: int, queries_failed: int, stages: tuple[StageCount, ...]
) -> SearchStatus:
    """Decide cómo terminó la búsqueda.

    Args:
        queries_ok: Consultas a proveedores que respondieron.
        queries_failed: Consultas que fallaron.
        stages: Conteos de las etapas por nota.

    Returns:
        ``failed`` si ningún proveedor respondió; ``partial`` si alguno
        falló o alguna etapa falló en más de la mitad; si no, ``completed``.
    """
    if queries_ok == 0:
        return SearchStatus.FAILED
    if queries_failed > 0 or any(s.failed_too_much for s in stages):
        return SearchStatus.PARTIAL
    return SearchStatus.COMPLETED


# Dominios de país de los medios que más se cuelan en búsquedas de México:
# Latinoamérica, España y Brasil (ISO 3166 alfa-3, igual que regions.code de
# los países). «PDI» es la policía de Chile y Google News traía decenas de
# medios .cl sin lugar en la nota (búsqueda del 09/11/2026). Los .com no dicen
# el país y se dejan sin decidir.
_COUNTRY_TLDS: dict[str, str] = {
    "mx": "MEX", "cl": "CHL", "pe": "PER", "ar": "ARG", "co": "COL", "ve": "VEN",
    "ec": "ECU", "bo": "BOL", "py": "PRY", "uy": "URY", "gt": "GTM", "hn": "HND",
    "sv": "SLV", "ni": "NIC", "cr": "CRI", "pa": "PAN", "do": "DOM", "cu": "CUB",
    "pr": "PRI", "es": "ESP", "br": "BRA",
}  # fmt: skip


def outlet_country(domain: str | None) -> str | None:
    """País de un medio según la terminación de su dominio, si la dice.

    Args:
        domain: Dominio del medio («adnradio.cl», «eluniversal.com.mx»).

    Returns:
        Clave ISO alfa-3 del país, o ``None`` si el dominio no dice el país.

    Example:
        >>> outlet_country("chilevision.cl")
        'CHL'
        >>> outlet_country("milenio.com") is None
        True
    """
    if not domain:
        return None
    return _COUNTRY_TLDS.get(domain.rsplit(".", 1)[-1].lower())


def in_region(
    primary: Place | None, searched: Place, outlet_domain: str | None = None
) -> bool | None:
    """Dice si la ubicación principal de una nota cae en la región buscada.

    Args:
        primary: Ubicación principal de la nota, si tiene.
        searched: Región de la búsqueda.
        outlet_domain: Dominio del medio. Si la nota no tiene ubicación y el
            medio es de otro país (``.cl``, ``.pe``…), cuenta como fuera.

    Returns:
        ``True``/``False`` según el prefijo de la clave o el país. Sin
        ubicación: ``False`` si se buscó un estado, municipio o localidad
        (no se puede asegurar que pasó ahí; Benji, 11/11/2026: «súper estricto
        de las zonas»), y ``None`` («Sin ubicación») si se buscó un país,
        salvo que el medio sea de otro país.
    """
    if primary is None:
        if searched.level is not RegionLevel.COUNTRY:
            return False
        country = outlet_country(outlet_domain)
        if country is not None and country != searched.country_code:
            return False
        return None
    if searched.level is RegionLevel.COUNTRY:
        return primary.country_code == searched.code
    return primary.region_id == searched.region_id or searched.contains(primary)
