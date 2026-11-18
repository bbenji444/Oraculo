"""Saldo real de la cuenta de SearchApi: ``GET /api/v1/me`` (ADR-0115).

Implementa ``CreditBalancePort``. Lo usa ``PlanSearch`` para que Google web
(y Google News de SearchApi) solo salga encendido, y solo se lance, si la
cuenta tiene saldo.

Documentación: https://www.searchapi.io/docs/account-api (consultada el
18/11/2026):

- ``GET https://www.searchapi.io/api/v1/me`` con la llave en
  ``Authorization: Bearer``. No gasta créditos (medido el 18/11/2026: tres
  llamadas y el saldo solo bajó con la búsqueda real, de 47 a 46).
- ``account.remaining_searches``: «the unused monthly allowance plus
  remaining_credits»; ``account.remaining_credits``: las búsquedas sueltas
  fuera del plan del mes. «At 0, searches are rejected». Se lee
  ``remaining_searches`` y, si no viene, ``remaining_credits``.

El saldo se guarda en memoria ``BALANCE_CACHE_SECONDS``: la pantalla de
búsqueda pide las fuentes cada vez que se abre y no hace falta preguntarle a
SearchApi cada vez. Si no se puede leer (red, 5xx, JSON raro) devuelve
``None`` y se vuelve a intentar a los ``BALANCE_RETRY_SECONDS``; quien lo usa
cae entonces al tope mensual local. Con la llave rechazada (401/403) el saldo
es 0: ninguna búsqueda pasaría.

No hace: no busca noticias ni guarda nada en la base.
"""

import asyncio
import json
import logging
import time
from collections.abc import Callable

from app.adapters.providers.http import ProviderHttpClient
from app.core.config import Settings
from app.domain.errors import ProviderAuthError, ProviderError
from app.domain.queries import Provider

logger = logging.getLogger(__name__)

ACCOUNT_URL = "https://www.searchapi.io/api/v1/me"
# Cinco minutos: lo que tarda en cambiar el saldo depende de las búsquedas de
# este mismo sistema, que además se cuentan en el tope local. Decisión del
# 18/11/2026 (revisión 1): «caché en memoria de pocos minutos».
BALANCE_CACHE_SECONDS = 300.0
# Si /me falló, se vuelve a preguntar al minuto en vez de esperar cinco.
BALANCE_RETRY_SECONDS = 60.0
# Es una consulta pequeña que hace esperar a la pantalla de búsqueda: si
# tarda más de 3 s se usa el tope local.
BALANCE_TIMEOUT_SECONDS = 3.0
# Un intento: el tope local cubre el hueco y el siguiente intento llega solo.
BALANCE_MAX_ATTEMPTS = 1
_ACCOUNT_FIELDS = ("remaining_searches", "remaining_credits")


def _remaining(body: str) -> int | None:
    """El saldo del cuerpo de ``/me``, o ``None`` si no viene como número entero."""
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        return None
    account = data.get("account") if isinstance(data, dict) else None
    if not isinstance(account, dict):
        return None
    for field in _ACCOUNT_FIELDS:
        value = account.get(field)
        # ``bool`` es subclase de ``int`` en Python: «true» no es un saldo.
        if isinstance(value, int) and not isinstance(value, bool):
            return max(0, value)
    return None


class SearchApiBalance:
    """``CreditBalancePort`` para la cuenta de SearchApi, con caché en memoria."""

    def __init__(
        self, http: ProviderHttpClient, clock: Callable[[], float] = time.monotonic
    ) -> None:
        """Recibe el cliente con la llave.

        Args:
            http: Cliente de SearchApi con la llave en sus encabezados.
            clock: Reloj en segundos; las pruebas pasan uno falso.
        """
        self._http = http
        self._clock = clock
        self._value: int | None = None
        self._expires_at = float("-inf")
        self._lock = asyncio.Lock()

    async def remaining(self) -> int | None:
        """Ver ``CreditBalancePort.remaining``.

        Returns:
            Búsquedas que le quedan a la cuenta (negativo cuenta como 0; la
            llave rechazada, también 0), o ``None`` si no se pudo leer.
        """
        async with self._lock:
            now = self._clock()
            if now < self._expires_at:
                return self._value
            value = await self._fetch()
            self._value = value
            wait = BALANCE_CACHE_SECONDS if value is not None else BALANCE_RETRY_SECONDS
            self._expires_at = now + wait
            return value

    async def _fetch(self) -> int | None:
        try:
            response = await self._http.get(ACCOUNT_URL, {})
        except ProviderAuthError:
            logger.warning("SearchApi rechazó la llave al leer el saldo: se toma como 0")
            return 0
        except ProviderError as error:
            logger.warning(f"No se pudo leer el saldo de SearchApi: {error.message}")
            return None
        value = _remaining(response.text)
        if value is None:
            logger.warning("SearchApi respondió /me sin un saldo legible")
        return value

    async def aclose(self) -> None:
        """Cierra las conexiones del cliente."""
        await self._http.aclose()


def build_searchapi_balance(settings: Settings) -> SearchApiBalance | None:
    """Crea el lector del saldo, si hay llave y la revisión está encendida.

    Args:
        settings: Configuración (``SEARCHAPI_API_KEY`` y
            ``SEARCHAPI_BALANCE_CHECK``).

    Returns:
        El lector, o ``None`` sin llave o con ``SEARCHAPI_BALANCE_CHECK=false``
        (entonces solo cuenta el tope mensual local).
    """
    key = settings.searchapi_api_key
    if key is None or not key.get_secret_value() or not settings.searchapi_balance_check:
        return None
    return SearchApiBalance(
        ProviderHttpClient(
            Provider.SEARCHAPI,
            timeout_seconds=BALANCE_TIMEOUT_SECONDS,
            max_attempts=BALANCE_MAX_ATTEMPTS,
            # Una consulta a la vez: el candado de ``remaining`` ya las junta.
            max_concurrency=1,
            # La llave va en el encabezado, nunca en la URL (como en las búsquedas).
            headers={"Authorization": f"Bearer {key.get_secret_value()}"},
        )
    )
