"""Catálogo de fuentes que el analista enciende o apaga en la búsqueda manual (F12.2).

Cada fuente es un ``Provider``. El catálogo dice cómo se llama en pantalla, si
cuesta créditos y si va encendida por defecto (ADR-0027). Las corridas
automáticas (F12.8) no usan switches: tienen su perfil fijo (ADR-0023).

``resolve_sources`` decide con qué fuentes corre una búsqueda a partir de lo
que pidió el analista y lo que está configurado.

No hace: no sabe si una fuente tiene su llave (eso lo dice cada adaptador con
``is_configured``) ni planea consultas.
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from app.domain.errors import InvalidRequestError
from app.domain.queries import Provider
from app.domain.query_dialects import DIALECTS


@dataclass(frozen=True, slots=True)
class Source:
    """Una fuente tal como la ve el analista.

    Attributes:
        provider: Proveedor.
        label: Nombre en pantalla.
        paid: Si gasta créditos (SearchApi) o es gratis.
        slow: Si tarda más que las demás porque abre un navegador real
            (BrowserWork, ADR-0028).
    """

    provider: Provider
    label: str
    paid: bool
    slow: bool = False


# En el orden en que se muestran. GDELT sigue apagado por su límite
# (ADR-0012) y queda fuera de los switches mientras tanto.
_SWITCHES = (
    Provider.GOOGLE_NEWS_RSS,
    Provider.LOCAL_INDEX,
    Provider.SEARCHAPI,
    Provider.BROWSERWORK_BING,
    Provider.BROWSERWORK_GOOGLE2,
)
# Abren un Chrome real en el servidor de BrowserWork: tardan minutos, no segundos.
_SLOW = frozenset({Provider.BROWSERWORK_BING, Provider.BROWSERWORK_GOOGLE2})
# El nombre y el costo salen de los dialectos de consulta: una sola lista para
# la estimación, «Probar concepto» y los switches.
SOURCES: tuple[Source, ...] = tuple(
    Source(p, DIALECTS[p].label, paid=DIALECTS[p].credits_per_query > 0, slow=p in _SLOW)
    for p in _SWITCHES
)
_BY_PROVIDER = {s.provider: s for s in SOURCES}


def source_of(provider: Provider) -> Source | None:
    """La fuente de un proveedor, si se ofrece como switch.

    Args:
        provider: Proveedor.

    Returns:
        Su fuente, o ``None`` si no se ofrece (GDELT).
    """
    return _BY_PROVIDER.get(provider)


def resolve_sources(
    requested: Sequence[Provider] | None,
    defaults: Iterable[Provider],
    configured: Iterable[Provider],
) -> tuple[Provider, ...]:
    """Fuentes con las que corre una búsqueda manual.

    Args:
        requested: Las que encendió el analista, o ``None`` si no eligió
            (se usan las de por defecto).
        defaults: Las encendidas por defecto (``MANUAL_DEFAULT_SOURCES``).
        configured: Las que tienen lo necesario para consultar.

    Returns:
        Las fuentes, sin repetir y en el orden de ``Provider`` (el de siempre).

    Raises:
        InvalidRequestError: Si no queda ninguna, o si el analista pidió
            una que no está configurada o no se ofrece.

    Example:
        >>> resolve_sources(None, [Provider.LOCAL_INDEX], [Provider.LOCAL_INDEX])
        (<Provider.LOCAL_INDEX: 'indice_local'>,)
    """
    ready = set(configured)
    if requested is None:
        chosen = {p for p in defaults if p in ready}
    else:
        chosen = set(requested)
        offered = [p for p in chosen if p not in _BY_PROVIDER]
        if offered:
            raise InvalidRequestError(
                "Esa fuente no se puede elegir.", {"fuentes": sorted(p.value for p in offered)}
            )
        missing = [p for p in chosen if p not in ready]
        if missing:
            names = ", ".join(_BY_PROVIDER[p].label for p in sorted(missing))
            raise InvalidRequestError(
                f"{names}: no está configurada; apágala o avisa a quien administra el sistema.",
                {"fuentes": sorted(p.value for p in missing)},
            )
    if not chosen:
        raise InvalidRequestError("Elige al menos una fuente para buscar.")
    return tuple(p for p in Provider if p in chosen)


def parse_sources(text: str) -> tuple[Provider, ...]:
    """Lee una lista de fuentes separadas por comas (``MANUAL_DEFAULT_SOURCES``).

    Args:
        text: Por ejemplo ``"google_news_rss,indice_local"``.

    Returns:
        Las fuentes, sin repetir y en el orden de ``Provider`` (el de siempre).

    Raises:
        ValueError: Si alguna no existe o no se ofrece como switch.
    """
    names = {name.strip() for name in text.split(",") if name.strip()}
    providers: set[Provider] = set()
    for name in names:
        provider = Provider(name)  # ValueError si no existe
        if provider not in _BY_PROVIDER:
            raise ValueError(f"{name} no se ofrece como fuente de la búsqueda manual")
        providers.add(provider)
    return tuple(p for p in Provider if p in providers)
