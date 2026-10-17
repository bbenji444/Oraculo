"""Presupuesto de una búsqueda: cuántas consultas y cuántos créditos (§7.2).

Dos topes, ambos para no gastar de más por error:

- **Por búsqueda:** ``MAX_QUERIES_PER_SEARCH`` consultas (10 por defecto).
  Si una búsqueda planea más, se rechaza completa **antes** de enviar nada.
- **Por mes:** ``SEARCHAPI_MONTHLY_CREDIT_LIMIT`` créditos de SearchApi. El
  mes es el calendario de la Ciudad de México. Si una consulta haría pasar
  el tope, esa consulta se salta (los proveedores gratuitos siguen).

No hace: no consulta la base; recibe los créditos ya gastados.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, tzinfo

from app.domain.errors import InvalidRequestError


class QueryBudgetExceededError(InvalidRequestError):
    """La búsqueda planea más consultas de las permitidas."""

    code = "query_budget_exceeded"


def check_query_count(planned: int, maximum: int) -> None:
    """Rechaza una búsqueda que planea demasiadas consultas.

    Args:
        planned: Consultas que se enviarían.
        maximum: Máximo permitido por búsqueda.

    Raises:
        QueryBudgetExceededError: Si ``planned`` pasa del máximo, con un
            mensaje que sugiere cómo reducirla.
    """
    if planned > maximum:
        raise QueryBudgetExceededError(
            f"La búsqueda generaría {planned} consultas y el máximo es {maximum}. "
            "Elige menos conceptos o conceptos con menos palabras clave.",
            {"consultas": planned, "maximo": maximum},
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
