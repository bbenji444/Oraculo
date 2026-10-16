"""Cliente HTTP compartido por los adaptadores de proveedores (ADR-0010).

Reúne en un solo lugar lo que la especificación §8 pide a cada adaptador:

1. **Tiempo máximo explícito** por petición.
2. **Reintentos con espera creciente** (1 s, 2 s, 4 s...) solo ante errores
   que pueden pasar solos: 429, 5xx, red caída o tiempo agotado.
3. **Sin reintento** ante llave rechazada (401/403) ni ante otros 4xx.
4. **Traducción a excepciones de dominio** (``ProviderError`` y familia).
5. **Límite de peticiones simultáneas** y, si el proveedor lo pide, una
   **pausa mínima entre peticiones** (GDELT).

Es el único lugar que crea clientes de ``httpx2``: si su API cambiara, el
impacto queda aquí.

No hace: no interpreta el contenido de la respuesta (eso es de cada adaptador)
y nunca registra la llave de un proveedor.
"""

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable, Mapping

import httpx2
from tenacity import (
    AsyncRetrying,
    RetryCallState,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from app.core.config import APP_VERSION
from app.domain.errors import (
    ProviderAuthError,
    ProviderError,
    ProviderRateLimitError,
    ProviderResponseError,
    ProviderUnavailableError,
)
from app.domain.queries import Provider

logger = logging.getLogger(__name__)

# Espera entre reintentos: 1 s, 2 s, 4 s... con tope de 8 s (backoff exponencial).
RETRY_WAIT_MIN_SECONDS = 1.0
RETRY_WAIT_MAX_SECONDS = 8.0
# Cuánto del cuerpo de un error se guarda en el mensaje: suficiente para
# entender qué pasó sin llenar el registro.
ERROR_BODY_CHARS = 300
# Nombre con que el sistema se presenta a los proveedores. Sin él, httpx2
# envía "python-httpx2/…", genérico; GDELT respondió 429 de forma
# persistente a ese cliente (16/10/2026) aun respetando su pausa de 5 s.
USER_AGENT = f"monitor-noticias/{APP_VERSION} (monitor de noticias geolocalizadas)"
_AUTH_STATUSES = frozenset({401, 403})
_TOO_MANY_REQUESTS = 429
_SERVER_ERROR = 500
_CLIENT_ERROR = 400

Sleep = Callable[[float], Awaitable[None]]


def _retryable(error: BaseException) -> bool:
    return isinstance(error, ProviderError) and error.retryable


def build_wait(rate_limit_wait_seconds: float) -> Callable[[RetryCallState], float]:
    """Cuánto esperar antes del siguiente intento.

    La espera normal crece 1 s, 2 s, 4 s... Si el proveedor respondió 429
    ("ve más despacio"), se espera al menos ``rate_limit_wait_seconds``:
    reintentar en 1 s solo empeora el bloqueo.

    Args:
        rate_limit_wait_seconds: Espera mínima tras un 429.

    Returns:
        La función de espera para tenacity.
    """
    exponential = wait_exponential(min=RETRY_WAIT_MIN_SECONDS, max=RETRY_WAIT_MAX_SECONDS)

    def wait(state: RetryCallState) -> float:
        base = exponential(state)
        error = state.outcome.exception() if state.outcome else None
        if isinstance(error, ProviderRateLimitError):
            return max(base, rate_limit_wait_seconds)
        return base

    return wait


class ProviderHttpClient:
    """Cliente HTTP de un proveedor, con reintentos, límites y errores de dominio."""

    def __init__(  # noqa: PLR0913 — configuración del cliente, todo por nombre (*)
        self,
        provider: Provider,
        *,
        timeout_seconds: float,
        max_attempts: int,
        max_concurrency: int,
        min_interval_seconds: float = 0.0,
        rate_limit_wait_seconds: float = 0.0,
        headers: Mapping[str, str] | None = None,
        transport: httpx2.AsyncBaseTransport | None = None,
        sleep: Sleep = asyncio.sleep,
    ) -> None:
        """Configura el cliente.

        Args:
            provider: Proveedor (para los mensajes de error).
            timeout_seconds: Tiempo máximo por petición.
            max_attempts: Intentos en total (1 = sin reintentos).
            max_concurrency: Peticiones simultáneas permitidas.
            min_interval_seconds: Pausa mínima entre el inicio de dos
                peticiones (0 = sin pausa).
            rate_limit_wait_seconds: Espera mínima antes de reintentar
                después de un 429.
            headers: Encabezados fijos (por ejemplo, la llave en
                ``Authorization``; nunca se registran).
            transport: Transporte de ``httpx2``; las pruebas pasan un
                ``MockTransport`` con respuestas grabadas.
            sleep: Función de espera; las pruebas la reemplazan para no esperar.
        """
        self._provider = provider
        self._max_attempts = max_attempts
        self._min_interval = min_interval_seconds
        self._wait = build_wait(rate_limit_wait_seconds)
        self._sleep = sleep
        self._semaphore = asyncio.Semaphore(max_concurrency)
        self._pace_lock = asyncio.Lock()
        self._last_start = float("-inf")
        self._client = httpx2.AsyncClient(
            timeout=httpx2.Timeout(timeout_seconds),
            headers={"User-Agent": USER_AGENT, **dict(headers or {})},
            transport=transport,
            follow_redirects=True,
        )

    def _log_retry(self, state: RetryCallState) -> None:
        """Deja en el registro cada intento fallido y la espera antes del siguiente.

        Sin esto, una respuesta final "200 sin resultados" no deja ver que
        antes hubo rechazos (diagnóstico de GDELT, 16/10/2026).
        """
        error = state.outcome.exception() if state.outcome else None
        wait = state.next_action.sleep if state.next_action else 0.0
        logger.warning(
            f"{self._provider.value}: intento {state.attempt_number} falló "
            f"({error}); siguiente intento en {wait:.0f} s"
        )

    async def aclose(self) -> None:
        """Cierra las conexiones abiertas."""
        await self._client.aclose()

    async def _pace(self) -> None:
        """Respeta la pausa mínima entre peticiones al mismo proveedor."""
        if self._min_interval <= 0:
            return
        async with self._pace_lock:
            wait = self._last_start + self._min_interval - time.monotonic()
            if wait > 0:
                await self._sleep(wait)
            self._last_start = time.monotonic()

    def _error_for(self, response: httpx2.Response) -> ProviderError | None:
        status = response.status_code
        if status < _CLIENT_ERROR:
            return None
        body = response.text[:ERROR_BODY_CHARS]
        name = self._provider.value
        if status in _AUTH_STATUSES:
            return ProviderAuthError(
                f"{name} rechazó la llave (HTTP {status}). Revisa la configuración.",
                provider=name,
                http_status=status,
            )
        if status == _TOO_MANY_REQUESTS:
            # El texto del proveedor dice qué ritmo espera (GDELT lo explica
            # en el cuerpo); se conserva para ajustar la pausa con evidencia.
            return ProviderRateLimitError(
                f"{name} pidió ir más despacio (HTTP 429): {body}",
                provider=name,
                http_status=status,
            )
        if status >= _SERVER_ERROR:
            return ProviderUnavailableError(
                f"{name} tuvo un error del servidor (HTTP {status}).",
                provider=name,
                http_status=status,
            )
        return ProviderResponseError(
            f"{name} rechazó la petición (HTTP {status}): {body}",
            provider=name,
            http_status=status,
        )

    async def _attempt(self, url: str, params: Mapping[str, str]) -> httpx2.Response:
        name = self._provider.value
        async with self._semaphore:
            await self._pace()
            try:
                response = await self._client.get(url, params=dict(params))
            except httpx2.TimeoutException as exc:
                raise ProviderUnavailableError(
                    f"{name} no respondió a tiempo.", provider=name
                ) from exc
            except httpx2.TransportError as exc:
                raise ProviderUnavailableError(
                    f"No se pudo conectar con {name}: {type(exc).__name__}.", provider=name
                ) from exc
        error = self._error_for(response)
        if error is not None:
            raise error
        return response

    async def get(self, url: str, params: Mapping[str, str]) -> httpx2.Response:
        """Hace un GET con reintentos y devuelve la respuesta exitosa.

        Args:
            url: Dirección del proveedor.
            params: Parámetros de la URL (sin la llave).

        Returns:
            La respuesta con código 2xx o 3xx.

        Raises:
            ProviderError: El último error, si todos los intentos fallaron, o
                el primero que no conviene reintentar.
        """
        retrying = AsyncRetrying(
            retry=retry_if_exception(_retryable),
            stop=stop_after_attempt(self._max_attempts),
            wait=self._wait,
            sleep=self._sleep,
            reraise=True,
        )
        retrying.before_sleep = self._log_retry
        response: httpx2.Response | None = None
        async for attempt in retrying:
            with attempt:
                response = await self._attempt(url, params)
        if response is None:  # pragma: no cover — tenacity siempre corre al menos un intento
            raise ProviderUnavailableError("Sin respuesta.", provider=self._provider.value)
        return response
