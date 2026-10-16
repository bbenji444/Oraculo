"""Fecha de "hoy" para los rangos de búsqueda.

"Últimos 7 días" depende de qué día es hoy, y el analista piensa en hora de
la Ciudad de México (CLAUDE.md §6.3), no en UTC: a las 20:00 del 15 de
octubre en CDMX ya es 16 en UTC.

Los casos de uso reciben esta función como dependencia para que las pruebas
puedan fijar la fecha.

No hace: no formatea fechas para mostrar.
"""

from collections.abc import Callable
from datetime import date, datetime
from zoneinfo import ZoneInfo

MEXICO_CITY = ZoneInfo("America/Mexico_City")

Today = Callable[[], date]


def mexico_city_today() -> date:
    """Fecha de hoy en la Ciudad de México.

    Returns:
        La fecha local.
    """
    return datetime.now(MEXICO_CITY).date()
