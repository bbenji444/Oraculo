"""Adaptador de BrowserWork: búsqueda web en Bing y en Google 2 con un Chrome real (ADR-0028).

BrowserWork es el servicio del jefe de Benji (``BROWSERWORK_BASE_URL``, por
ejemplo ``http://192.168.0.37:8787``). Abre un Chrome de verdad, busca y
devuelve los resultados. Su API es asíncrona (leída de su código el
24/10/2026, solo lectura):

- ``POST /api/search {query, pages, engines: ["bing"|"google2"]}`` → ``{id, status: "queued"}``.
- ``GET /api/search/{id}`` → ``status``: ``queued``, ``running``, ``done``,
  ``error`` o ``awaiting_captcha`` (espera a que una persona resuelva un
  captcha, hasta 600 s).
- ``GET /api/search/{id}/results`` → ``{results: [{title, url, site_name,
  description, rank, …}]}``. **Sin fecha**: las notas quedan con
  ``published_at=None``.
- ``POST /search/{id}/abort`` cancela un trabajo que espera captcha. A uno
  que ya está corriendo no lo detiene: termina solo en su servidor.

Corre **un trabajo a la vez** para todos sus usuarios, así que el adaptador
espera con un tope (``BROWSERWORK_TIMEOUT_SECONDS``) y, si se vence o pide
captcha, deja la fuente fallida (la búsqueda queda ``partial``) en lugar de
esperar a una persona.

Reglas (ADR-0023, ADR-0028): sin llave ni credenciales; solo consulta los
trabajos que él mismo creó (nunca lista ``/api/searches``, que trae los de
otras personas); no cambia nada del servidor.

No hace: no decide la relevancia ni la fecha de las notas (eso es de la IA).
"""

import asyncio
import json
import time
from collections.abc import Awaitable, Callable, Mapping
from typing import Any

from app.adapters.providers.http import ProviderHttpClient
from app.application.ports.providers import ProviderResponse
from app.domain.articles import InvalidArticleError, RawArticle, domain_of
from app.domain.errors import (
    ProviderError,
    ProviderNotConfiguredError,
    ProviderResponseError,
    ProviderUnavailableError,
)
from app.domain.queries import PlannedQuery, Provider

# Motor de BrowserWork de cada proveedor (``app/engines.py`` de BrowserWork).
ENGINES: Mapping[Provider, str] = {
    Provider.BROWSERWORK_BING: "bing",
    Provider.BROWSERWORK_GOOGLE2: "google2",
}
NOT_CONFIGURED_MESSAGE = (
    "BrowserWork no está configurado (falta BROWSERWORK_BASE_URL en .env, "
    "por ejemplo http://192.168.0.37:8787)."
)
_DONE = "done"
_ERROR = "error"
_CAPTCHA = "awaiting_captcha"
# Estados en los que el trabajo todavía no termina.
_WAITING = frozenset({"queued", "running"})

Sleep = Callable[[float], Awaitable[None]]
Clock = Callable[[], float]


def parse_results(body: Mapping[str, Any], provider: Provider) -> tuple[list[RawArticle], int]:
    """Convierte los resultados de BrowserWork al formato común.

    Args:
        body: Respuesta de ``/api/search/{id}/results``.
        provider: Proveedor (``browserwork_bing`` o ``browserwork_google2``).

    Returns:
        Las notas y cuántos resultados se descartaron (sin URL o título).

    Raises:
        ProviderResponseError: Si la respuesta no trae la lista ``results``.
    """
    results = body.get("results")
    if not isinstance(results, list):
        raise ProviderResponseError(
            "BrowserWork respondió sin lista de resultados.", provider=provider.value
        )
    articles: list[RawArticle] = []
    discarded = 0
    for position, item in enumerate(results, start=1):
        if not isinstance(item, Mapping):
            discarded += 1
            continue
        url = str(item.get("url") or "")
        try:
            articles.append(
                RawArticle.create(
                    provider=provider,
                    provider_rank=int(item.get("rank") or position),
                    url=url,
                    title=str(item.get("title") or ""),
                    source_name=str(item.get("site_name") or "") or None,
                    source_domain=domain_of(url) if url else None,
                    # BrowserWork no da fecha: la IA marca la del hecho (ADR-0028).
                    published_at=None,
                    snippet=str(item.get("description") or "") or None,
                    raw=dict(item),
                )
            )
        except InvalidArticleError:
            discarded += 1
    return articles, discarded


class BrowserWorkProvider:
    """``NewsProviderPort`` para un motor de BrowserWork.

    Args:
        provider: ``Provider.BROWSERWORK_BING`` o ``Provider.BROWSERWORK_GOOGLE2``.
        http: Cliente HTTP (timeout, reintentos y concurrencia).
        base_url: Dirección de BrowserWork, o ``None`` si no está configurado.
        pages: Páginas por búsqueda (``BROWSERWORK_PAGES``).
        timeout_seconds: Tope total de espera por búsqueda.
        poll_seconds: Cada cuánto se pregunta el estado del trabajo.
        sleep: Espera (las pruebas la reemplazan para no esperar).
        clock: Reloj monótono (las pruebas lo adelantan).
    """

    def __init__(  # noqa: PLR0913 — configuración del adaptador, todo por nombre (*)
        self,
        provider: Provider,
        http: ProviderHttpClient,
        *,
        base_url: str | None,
        pages: int,
        timeout_seconds: float,
        poll_seconds: float,
        sleep: Sleep = asyncio.sleep,
        clock: Clock = time.monotonic,
    ) -> None:
        if provider not in ENGINES:
            raise ValueError(f"{provider} no es un motor de BrowserWork")
        self._provider = provider
        self._http = http
        self._base = base_url.rstrip("/") if base_url else None
        self._pages = pages
        self._timeout = timeout_seconds
        self._poll = poll_seconds
        self._sleep = sleep
        self._clock = clock

    @property
    def provider(self) -> Provider:
        """El proveedor de este adaptador."""
        return self._provider

    def is_configured(self) -> bool:
        """Con ``BROWSERWORK_BASE_URL`` en ``.env``."""
        return self._base is not None

    def request_params(self, query: PlannedQuery) -> dict[str, str]:
        """Ver ``NewsProviderPort.request_params``."""
        return {
            "query": query.text,
            "pages": str(self._pages),
            "engines": ENGINES[self._provider],
        }

    def estimate_cost(self, query: PlannedQuery) -> int:
        """Gratis: BrowserWork no cobra por consulta."""
        return 0

    async def search(self, query: PlannedQuery) -> ProviderResponse:
        """Ver ``NewsProviderPort.search``.

        Raises:
            ProviderNotConfiguredError: Sin ``BROWSERWORK_BASE_URL``.
            ProviderUnavailableError: Si pide captcha, falla o se vence el tope.
            ProviderResponseError: Si responde con un formato inesperado.
        """
        if self._base is None:
            raise ProviderNotConfiguredError(NOT_CONFIGURED_MESSAGE, provider=self._provider.value)
        params = self.request_params(query)
        created = await self._http.post_json(
            f"{self._base}/api/search",
            {"query": query.text, "pages": self._pages, "engines": [ENGINES[self._provider]]},
        )
        job_id = str(self._json(created.text).get("id") or "")
        if not job_id:
            raise ProviderResponseError(
                "BrowserWork no devolvió el id del trabajo.", provider=self._provider.value
            )
        await self._wait_until_done(job_id)
        results = await self._http.get(f"{self._base}/api/search/{job_id}/results", {})
        articles, discarded = parse_results(self._json(results.text), self._provider)
        return ProviderResponse(
            articles=tuple(articles),
            http_status=results.status_code,
            params={**params, "job_id": job_id},
            body=results.text,
            discarded=discarded,
            pages=self._pages,
        )

    async def _wait_until_done(self, job_id: str) -> None:
        deadline = self._clock() + self._timeout
        while True:
            job = self._json((await self._http.get(f"{self._base}/api/search/{job_id}", {})).text)
            status = str(job.get("status") or "")
            if status == _DONE:
                return
            if status == _CAPTCHA:
                await self._abort(job_id)
                raise self._unavailable(
                    "pidió un captcha; la fuente se omitió en esta búsqueda", job_id
                )
            if status == _ERROR or status not in _WAITING:
                raise self._unavailable(f"falló ({job.get('error') or status})", job_id)
            if self._clock() >= deadline:
                raise self._unavailable(
                    f"no terminó en {int(self._timeout)} s "
                    "(su navegador atiende una búsqueda a la vez)",
                    job_id,
                )
            await self._sleep(self._poll)

    async def _abort(self, job_id: str) -> None:
        """Libera el navegador del servidor si nuestro trabajo espera un captcha."""
        try:
            await self._http.post_json(f"{self._base}/search/{job_id}/abort", {})
        except ProviderError:
            # Si no se pudo cancelar, el trabajo se vence solo en su servidor
            # (CAPTCHA_WAIT_S); la búsqueda sigue igual.
            return

    def _unavailable(self, what: str, job_id: str) -> ProviderUnavailableError:
        label = "Bing" if self._provider is Provider.BROWSERWORK_BING else "Google 2"
        return ProviderUnavailableError(
            f"BrowserWork ({label}) {what}.",
            provider=self._provider.value,
            details={"trabajo": job_id},
        )

    def _json(self, text: str) -> Mapping[str, Any]:
        try:
            data = json.loads(text)
        except json.JSONDecodeError as error:
            raise ProviderResponseError(
                "BrowserWork respondió algo que no es JSON.", provider=self._provider.value
            ) from error
        if not isinstance(data, dict):
            raise ProviderResponseError(
                "BrowserWork respondió un JSON inesperado.", provider=self._provider.value
            )
        return data
