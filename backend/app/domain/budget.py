"""Presupuesto de una búsqueda: cuántas consultas y cuántos créditos (§7.2).

Tres topes, todos para no gastar ni saturar a nadie por error:

- **Consultas de pago por búsqueda:** ``MAX_QUERIES_PER_SEARCH`` (10 por
  defecto). Cuenta solo las que cuestan créditos (SearchApi).
- **Consultas gratuitas por búsqueda:** ``MAX_FREE_QUERIES_PER_SEARCH`` (24
  por defecto, ADR-0109). Cuenta las que van a un buscador de afuera que no
  cobra (Google News RSS, GDELT, BrowserWork): no cuestan, pero si se les
  pide mucho seguido frenan las peticiones. El índice local no cuenta: es
  nuestra base.

  Si una búsqueda pasa cualquiera de los dos, se rechaza completa **antes**
  de enviar nada.
- **Por mes:** ``SEARCHAPI_MONTHLY_CREDIT_LIMIT`` créditos de SearchApi. El
  mes es el calendario de la Ciudad de México. Si una consulta haría pasar
  el tope, esa consulta se salta (los proveedores gratuitos siguen). Google
  News y Google web usan la misma cuenta de SearchApi (``credit_account``,
  ADR-0115): el tope y lo gastado en el mes son de los dos juntos.

No hace: no consulta la base; recibe los créditos ya gastados.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, tzinfo

from app.domain.errors import InvalidRequestError
from app.domain.queries import Provider
from app.domain.query_dialects import DIALECTS, FREE, SEARCHAPI_ACCOUNT

# Nombre de cada cuenta de créditos para los mensajes (ADR-0115).
ACCOUNT_LABELS = {SEARCHAPI_ACCOUNT: "SearchApi (noticias + web)"}

# Aviso cuando Google web no alcanza créditos (tope del mes o SearchApi sin
# saldo): la búsqueda sigue con las fuentes de noticias (ADR-0115). Lo usan la
# búsqueda rápida y sus pruebas, para que diga siempre lo mismo.
NO_WEB_CREDITS_NOTICE = "Sin créditos de Google web: se buscó en noticias"


def credit_account(provider: Provider) -> str:
    """Cuenta de créditos que gasta un proveedor.

    Args:
        provider: Proveedor.

    Returns:
        La cuenta compartida (``searchapi`` para Google News y Google web) o,
        si no comparte, el nombre del propio proveedor.
    """
    return DIALECTS[provider].credit_account or provider.value


def account_providers(provider: Provider) -> tuple[Provider, ...]:
    """Proveedores que gastan la misma cuenta que ``provider``, en su orden.

    Args:
        provider: Proveedor.

    Returns:
        Todos los que comparten su cuenta, incluido él.

    Example:
        >>> account_providers(Provider.SEARCHAPI)
        (<Provider.SEARCHAPI: 'searchapi'>, <Provider.SEARCHAPI_WEB: 'searchapi_web'>)
    """
    account = credit_account(provider)
    return tuple(p for p in Provider if credit_account(p) == account)


def account_label(provider: Provider) -> str:
    """Nombre en pantalla de la cuenta de créditos de un proveedor.

    Args:
        provider: Proveedor.

    Returns:
        «SearchApi (noticias + web)», o el nombre del dialecto si no comparte.
    """
    return ACCOUNT_LABELS.get(credit_account(provider), DIALECTS[provider].label)


class QueryBudgetExceededError(InvalidRequestError):
    """La búsqueda planea más consultas de las permitidas."""

    code = "query_budget_exceeded"


@dataclass(frozen=True, slots=True)
class QueryCaps:
    """Topes de consultas de una búsqueda (``.env``).

    Attributes:
        paid: ``MAX_QUERIES_PER_SEARCH``: consultas que cuestan créditos.
        free: ``MAX_FREE_QUERIES_PER_SEARCH``: consultas gratuitas a
            buscadores de afuera.
    """

    paid: int
    free: int


def check_query_count(providers: Sequence[Provider], caps: QueryCaps) -> None:
    """Rechaza una búsqueda que planea demasiadas consultas.

    Args:
        providers: El proveedor de cada consulta que se enviaría.
        caps: Topes por búsqueda.

    Raises:
        QueryBudgetExceededError: Si las de pago o las gratuitas pasan su
            tope, con un mensaje que sugiere cómo reducirla.

    Example:
        >>> check_query_count([Provider.GOOGLE_NEWS_RSS] * 25, QueryCaps(10, 24))
        QueryBudgetExceededError: ...25 consultas a buscadores gratuitos...
    """
    dialects = [DIALECTS[p] for p in providers]
    paid = sum(1 for d in dialects if d.credits_per_query > FREE)
    free = sum(1 for d in dialects if d.credits_per_query == FREE and d.external)
    if paid > caps.paid:
        raise QueryBudgetExceededError(
            f"La búsqueda generaría {paid} consultas de pago y el máximo es {caps.paid}. "
            "Elige menos conceptos o conceptos con menos palabras clave.",
            {"consultas": paid, "maximo": caps.paid, "tipo": "pago"},
        )
    if free > caps.free:
        raise QueryBudgetExceededError(
            f"La búsqueda generaría {free} consultas a buscadores gratuitos y el máximo "
            f"es {caps.free}. Elige menos conceptos o quita frases a los conceptos "
            "«como en Google»: cada frase es una consulta.",
            {"consultas": free, "maximo": caps.free, "tipo": "gratuitas"},
        )


def month_start(now: datetime, tz: tzinfo) -> datetime:
    """Inicio del mes calendario en ``tz``, expresado en UTC.

    Args:
        now: Momento actual (con zona).
        tz: Zona en que se cuenta el mes (la de la Ciudad de México).

    Returns:
        El día 1 a las 00:00 en ``tz``, en UTC.

    Example:
        >>> month_start(datetime(2026, 11, 1, 3, 0, tzinfo=UTC), MEXICO_CITY)
        datetime(2026, 10, 1, 6, 0, tzinfo=UTC)  # aún es octubre en la CDMX
    """
    local = now.astimezone(tz)
    return local.replace(day=1, hour=0, minute=0, second=0, microsecond=0).astimezone(UTC)


@dataclass(slots=True)
class MonthlyCredits:
    """Créditos de un proveedor de pago en el mes, durante una ejecución.

    Lleva la cuenta de lo ya gastado más lo reservado por esta ejecución,
    para que dos consultas simultáneas no pasen juntas el tope.

    Attributes:
        used: Créditos gastados en el mes antes de esta ejecución.
        limit: Tope mensual.
        reserved: Créditos reservados por esta ejecución.
    """

    used: int
    limit: int
    reserved: int = 0

    def try_reserve(self, cost: int) -> bool:
        """Reserva créditos si caben en el tope.

        Args:
            cost: Créditos de la consulta.

        Returns:
            ``True`` si se reservaron; ``False`` si pasarían el tope.
        """
        if self.used + self.reserved + cost > self.limit:
            return False
        self.reserved += cost
        return True

    def release(self, cost: int) -> None:
        """Devuelve créditos reservados (la consulta falló y no se cobró).

        Args:
            cost: Créditos a devolver.
        """
        self.reserved = max(0, self.reserved - cost)
