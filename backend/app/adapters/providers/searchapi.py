"""Adaptador de SearchApi, motor ``google_news`` (especificación §8).

Resultados reales de Google News, de pago (1 crédito por búsqueda exitosa).

Documentación: https://www.searchapi.io/docs/google-news
- ``GET /api/v1/search?engine=google_news&q=…``; la llave va en el
  encabezado ``Authorization: Bearer`` (nunca en la URL ni en los registros).
- País e idioma: ``gl`` y ``hl``. Tiempo: ``time_period`` (``last_day``,
  ``last_week``, ``last_month``…) o ``time_period_min``/``time_period_max``
  en ``MM/DD/YYYY``.
- ``link=resolved`` entrega la URL real del medio en lugar de la redirección
  de Google: indispensable para deduplicar en F4.
- Responde ``organic_results`` con ``position``, ``title``, ``link``,
  ``source``, ``date`` y ``snippet``. Según https://www.searchapi.io/pricing
  solo se cobran las respuestas 200.

VERIFICAR con la primera respuesta real: formato de ``date`` (relativo, como
"hace 19 horas") y si existe ``iso_date``; cuántos resultados trae una página.

No hace: no pide más de una página por consulta (cada página es 1 crédito).
"""

import json
from datetime import datetime

from app.adapters.providers.http import ProviderHttpClient
from app.application.ports.providers import ProviderResponse
from app.domain.articles import InvalidArticleError, RawArticle
from app.domain.errors import ProviderNotConfiguredError, ProviderResponseError
from app.domain.queries import DateWindow, PlannedQuery, Provider

SEARCHAPI_URL = "https://www.searchapi.io/api/v1/search"
ENGINE = "google_news"
LANGUAGE = "es"
# Si un país no tiene código ISO-2, se usa México (foco del sistema).
FALLBACK_COUNTRY = "mx"
# Una búsqueda exitosa = 1 crédito (página de precios de SearchApi).
CREDITS_PER_QUERY = 1
# Rangos relativos que SearchApi entiende sin fechas fijas.
_RELATIVE_PERIODS = {1: "last_day", 7: "last_week", 30: "last_month"}
_US_DATE = "%m/%d/%Y"


def time_params(window: DateWindow) -> dict[str, str]:
    """Parámetros de tiempo de SearchApi.

    Args:
        window: Rango de la búsqueda.

    Returns:
        ``time_period`` para 1, 7 o 30 días; si no, ``time_period_min`` y
        ``time_period_max`` en ``MM/DD/YYYY``.
    """
    period = _RELATIVE_PERIODS.get(window.relative_days or 0)
    if period is not None:
        return {"time_period": period}
    return {
        "time_period_min": window.date_from.strftime(_US_DATE),
        "time_period_max": window.date_to.strftime(_US_DATE),
    }


def _published(item: dict[str, object]) -> datetime | None:
    value = item.get("iso_date")
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else None


def _source_name(value: object) -> str | None:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        name = value.get("name")
        return name if isinstance(name, str) else None
    return None


def parse_results(body: str) -> tuple[list[RawArticle], int]:
    """Convierte la respuesta JSON de SearchApi en notas del formato común.

    Args:
        body: Cuerpo de la respuesta.

    Returns:
        Las notas válidas y cuántos resultados se descartaron.

    Raises:
        ProviderResponseError: Si el cuerpo no es JSON o trae un error.
    """
    try:
        data = json.loads(body)
    except json.JSONDecodeError as exc:
        raise ProviderResponseError(
            f"SearchApi no respondió JSON: {body[:200]}", provider=Provider.SEARCHAPI.value
        ) from exc
    if not isinstance(data, dict):
        raise ProviderResponseError("SearchApi respondió un JSON inesperado.", provider="searchapi")
    if isinstance(data.get("error"), str):
        raise ProviderResponseError(f"SearchApi: {data['error']}", provider="searchapi")
    items = data.get("organic_results", [])
    if not isinstance(items, list):
        raise ProviderResponseError(
            "SearchApi: 'organic_results' no es una lista.", provider="searchapi"
        )
    articles: list[RawArticle] = []
    discarded = 0
    for index, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            discarded += 1
            continue
        position = item.get("position")
        try:
            articles.append(
                RawArticle.create(
                    provider=Provider.SEARCHAPI,
                    provider_rank=position if isinstance(position, int) else index,
                    url=str(item.get("link", "")),
                    title=item.get("title"),
                    source_name=_source_name(item.get("source")),
                    published_at=_published(item),
                    snippet=item.get("snippet"),
                    raw=item,
                )
            )
        except InvalidArticleError:
            discarded += 1
    return articles, discarded


class SearchApiProvider:
    """``NewsProviderPort`` para SearchApi (Google News)."""

    def __init__(self, http: ProviderHttpClient | None) -> None:
        """Recibe el cliente HTTP con la llave en sus encabezados.

        Args:
            http: Cliente HTTP, o ``None`` si no hay llave configurada.
        """
        self._http = http

    @property
    def provider(self) -> Provider:
        """Ver ``NewsProviderPort.provider``."""
        return Provider.SEARCHAPI

    def is_configured(self) -> bool:
        """Solo funciona con ``SEARCHAPI_API_KEY`` en ``.env``."""
        return self._http is not None

    def request_params(self, query: PlannedQuery) -> dict[str, str]:
        """Ver ``NewsProviderPort.request_params`` (la llave no va aquí)."""
        return {
            "engine": ENGINE,
            "q": query.text,
            "gl": (query.country.iso_a2 or FALLBACK_COUNTRY).lower(),
            "hl": LANGUAGE,
            "link": "resolved",
            **time_params(query.window),
        }

    def estimate_cost(self, query: PlannedQuery) -> int:
        """Una página por consulta: 1 crédito."""
        return CREDITS_PER_QUERY

    async def search(self, query: PlannedQuery) -> ProviderResponse:
        """Ver ``NewsProviderPort.search``.

        Raises:
            ProviderNotConfiguredError: Si falta la llave.
        """
        if self._http is None:
            raise ProviderNotConfiguredError(
                "Falta SEARCHAPI_API_KEY en .env.", provider=Provider.SEARCHAPI.value
            )
        params = self.request_params(query)
        response = await self._http.get(SEARCHAPI_URL, params)
        articles, discarded = parse_results(response.text)
        return ProviderResponse(
            articles=tuple(articles),
            http_status=response.status_code,
            params=params,
            body=response.text,
            discarded=discarded,
        )
