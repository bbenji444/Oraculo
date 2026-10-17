"""Adaptador de GDELT DOC 2.0 (especificación §8): gratuito, cobertura amplia.

Traduce una ``PlannedQuery`` a una petición de GDELT y su respuesta JSON a
``RawArticle``. El texto de la consulta ya trae ``sourcelang:spanish`` y
``sourcecountry:<FIPS>`` (dialecto de ``app.domain.query_dialects``); aquí
solo se agregan los parámetros de la URL.

Documentación: https://blog.gdeltproject.org/gdelt-doc-2-0-api-debuts/
(``mode=ArtList``, ``format=json``, ``maxrecords`` hasta 250, ``timespan`` o
``startdatetime``/``enddatetime`` en ``YYYYMMDDHHMMSS`` dentro de los últimos
3 meses, ``sort``).

No hace: no deduplica ni lee las notas.
"""

import json
from datetime import UTC, date, datetime, time

from app.adapters.providers.http import ProviderHttpClient
from app.application.clock import MEXICO_CITY
from app.application.ports.providers import ProviderResponse
from app.domain.articles import InvalidArticleError, RawArticle
from app.domain.errors import (
    ProviderNotConfiguredError,
    ProviderRateLimitError,
    ProviderResponseError,
)
from app.domain.queries import DateWindow, PlannedQuery, Provider

GDELT_URL = "https://api.gdeltproject.org/api/v2/doc/doc"
DISABLED_MESSAGE = (
    "GDELT está desactivado: respondió 429 de forma persistente y vacío después de "
    "los rechazos (ADR-0012). Para el reintento diario: make gdelt-diagnostico."
)
# Cuerpos que GDELT usa para "sin resultados" (medido: "{}").
_EMPTY_BODIES = frozenset({"", "{}"})
# Máximo documentado de resultados en ArtList.
MAX_RECORDS = 250
# Más recientes primero: en monitoreo importa no perder lo nuevo.
SORT = "DateDesc"
_GDELT_DATETIME = "%Y%m%d%H%M%S"
# Formato de "seendate" (no documentado en la página de DOC 2.0), confirmado
# con respuestas reales del 16/10/2026: "20261016T021500Z", en UTC
# (fixture gdelt_jalisco_1d.json).
_SEENDATE = "%Y%m%dT%H%M%SZ"
_END_OF_DAY = time(23, 59, 59)


def _utc_stamp(day: date, at: time) -> str:
    """Fecha local de la Ciudad de México → texto UTC que espera GDELT."""
    return datetime.combine(day, at, tzinfo=MEXICO_CITY).astimezone(UTC).strftime(_GDELT_DATETIME)


def time_params(window: DateWindow) -> dict[str, str]:
    """Parámetros de tiempo: ``timespan`` relativo o fechas fijas en UTC.

    Args:
        window: Rango de la búsqueda (días en hora de la Ciudad de México).

    Returns:
        ``{"timespan": "7d"}`` o ``{"startdatetime": ..., "enddatetime": ...}``.
    """
    if window.relative_days is not None:
        return {"timespan": f"{window.relative_days}d"}
    return {
        "startdatetime": _utc_stamp(window.date_from, time.min),
        "enddatetime": _utc_stamp(window.date_to, _END_OF_DAY),
    }


def _parse_seendate(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.strptime(value, _SEENDATE).replace(tzinfo=UTC)
    except ValueError:
        return None


def parse_articles(body: str) -> tuple[list[RawArticle], int]:
    """Convierte la respuesta JSON de GDELT en notas del formato común.

    GDELT responde algunos errores como texto plano con código 200 (por
    ejemplo, una consulta mal formada); eso se reporta como error de
    respuesta con el texto original.

    Args:
        body: Cuerpo de la respuesta.

    Returns:
        Las notas válidas y cuántos resultados se descartaron.

    Raises:
        ProviderResponseError: Si el cuerpo no es el JSON esperado.
    """
    stripped = body.strip()
    if not stripped:
        return [], 0
    try:
        data = json.loads(stripped)
    except json.JSONDecodeError as exc:
        raise ProviderResponseError(
            f"GDELT respondió texto en lugar de JSON: {stripped[:300]}", provider="gdelt"
        ) from exc
    # VERIFICAR: sin resultados, GDELT podría responder {} en lugar de una lista vacía.
    items = data.get("articles", []) if isinstance(data, dict) else None
    if not isinstance(items, list):
        raise ProviderResponseError("GDELT respondió un JSON sin 'articles'.", provider="gdelt")
    articles: list[RawArticle] = []
    discarded = 0
    for rank, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            discarded += 1
            continue
        try:
            articles.append(
                RawArticle.create(
                    provider=Provider.GDELT,
                    provider_rank=rank,
                    url=str(item.get("url", "")),
                    title=item.get("title"),
                    source_domain=item.get("domain"),
                    published_at=_parse_seendate(item.get("seendate")),
                    language=item.get("language"),
                    raw=item,
                )
            )
        except InvalidArticleError:
            discarded += 1
    return articles, discarded


class GdeltProvider:
    """``NewsProviderPort`` para GDELT DOC 2.0 (desactivado por defecto, ADR-0012)."""

    def __init__(self, http: ProviderHttpClient, *, enabled: bool) -> None:
        """Recibe el cliente HTTP ya configurado (con la pausa entre peticiones).

        Args:
            http: Cliente HTTP de GDELT.
            enabled: ``GDELT_ENABLED``. Si es ``False`` no consulta nada.
        """
        self._http = http
        self._enabled = enabled

    @property
    def provider(self) -> Provider:
        """Ver ``NewsProviderPort.provider``."""
        return Provider.GDELT

    def is_configured(self) -> bool:
        """Solo con ``GDELT_ENABLED=true`` (desactivado por defecto, ADR-0012)."""
        return self._enabled

    def request_params(self, query: PlannedQuery) -> dict[str, str]:
        """Ver ``NewsProviderPort.request_params``."""
        return {
            "query": query.text,
            "mode": "ArtList",
            "format": "json",
            "maxrecords": str(MAX_RECORDS),
            "sort": SORT,
            **time_params(query.window),
        }

    def estimate_cost(self, query: PlannedQuery) -> int:
        """GDELT es gratuito."""
        return 0

    async def search(self, query: PlannedQuery) -> ProviderResponse:
        """Ver ``NewsProviderPort.search``.

        Raises:
            ProviderNotConfiguredError: Si está desactivado.
            ProviderRateLimitError: Si respondió vacío después de rechazos
                429: no se sabe si no hay notas o si nos estaba limitando.
        """
        if not self._enabled:
            raise ProviderNotConfiguredError(DISABLED_MESSAGE, provider=Provider.GDELT.value)
        params = self.request_params(query)
        outcome = await self._http.get_with_history(GDELT_URL, params)
        response = outcome.response
        if outcome.rate_limited and response.text.strip() in _EMPTY_BODIES:
            # Decisión de Benji (ADR-0012): un {} tras un 429 es falla, nunca
            # "sin resultados". En el diagnóstico del 16/10/2026, "gobierno"
            # en notas en español de un día llegó vacío justo después de 429.
            raise ProviderRateLimitError(
                f"GDELT respondió vacío después de {outcome.rate_limited} rechazo(s) 429: "
                "se registra como falla, no como 'sin resultados' (ADR-0012).",
                provider=Provider.GDELT.value,
                http_status=response.status_code,
            )
        articles, discarded = parse_articles(response.text)
        return ProviderResponse(
            articles=tuple(articles),
            http_status=response.status_code,
            params=params,
            body=response.text,
            discarded=discarded,
        )
