"""Fechas de los resultados de la búsqueda web de Google y si caen en el periodo (ADR-0115).

Google web no da la fecha exacta como Google News (``iso_date``): da un texto
libre, y muchas veces ninguno. En la respuesta real del 18/11/2026 («hacker
eternal», ``hl=es``) vinieron «hace 15 horas» y «hace 5 días»; la
documentación de SearchApi muestra «Nov 30, 2022» y, en foros, «21h ago».

``parse_result_date`` entiende esos formatos y **nunca inventa**: si no
entiende el texto devuelve ``None``. Las fechas relativas («hace 5 días») se
cuentan desde ``now`` y por eso tienen un día de redondeo. Desde la revisión
del 18/11/2026 también entiende meses y años («hace 3 meses», «2 years ago»)
y fechas sin año («17 nov»): sin ellas, una nota que Google marca como vieja
quedaba sin fecha y se colaba a la ventana de una búsqueda manual.

``kept_by_window`` decide qué pasa con una nota sin fecha en el periodo
estricto de una búsqueda: en las manuales se queda si la trajo un buscador
que ya filtró por fecha (``trusts_window``, Google web con ``time_period``);
en las corridas automáticas, nunca.

No hace: no consulta a nadie; recibe el texto y la hora actual.
"""

import re
from collections.abc import Iterable
from datetime import UTC, date, datetime, time, timedelta, tzinfo

from app.domain.queries import Provider
from app.domain.query_dialects import DIALECTS
from app.domain.schedule import RunWindow

# Una fecha sin hora («17 nov 2026») se fija a mediodía local: es el punto
# medio del día y no sesga las comparaciones de ±1 día de los duplicados.
DATE_ONLY_HOUR = time(12, 0)
# Meses por sus tres primeras letras, en español y en inglés (los dos idiomas
# que puede devolver Google según ``hl``). «sept» y «set» son de septiembre.
_MONTHS = {
    "ene": 1,
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "abr": 4,
    "apr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "ago": 8,
    "aug": 8,
    "sep": 9,
    "set": 9,
    "oct": 10,
    "nov": 11,
    "dic": 12,
    "dec": 12,
}
# Un mes y un año de las fechas relativas («hace 3 meses», «2 years ago»).
# Google redondea a meses o años enteros, así que la fecha es aproximada; basta
# para saber que la nota no es de la semana que se busca.
DAYS_PER_MONTH = 30
DAYS_PER_YEAR = 365
# Unidades de las fechas relativas, en español e inglés.
_UNITS = {
    "min": timedelta(minutes=1),
    "minuto": timedelta(minutes=1),
    "minutos": timedelta(minutes=1),
    "minute": timedelta(minutes=1),
    "minutes": timedelta(minutes=1),
    "mins": timedelta(minutes=1),
    "h": timedelta(hours=1),
    "hr": timedelta(hours=1),
    "hrs": timedelta(hours=1),
    "hora": timedelta(hours=1),
    "horas": timedelta(hours=1),
    "hour": timedelta(hours=1),
    "hours": timedelta(hours=1),
    "d": timedelta(days=1),
    "dia": timedelta(days=1),
    "dias": timedelta(days=1),
    "day": timedelta(days=1),
    "days": timedelta(days=1),
    "w": timedelta(weeks=1),
    "semana": timedelta(weeks=1),
    "semanas": timedelta(weeks=1),
    "week": timedelta(weeks=1),
    "weeks": timedelta(weeks=1),
    "mes": timedelta(days=DAYS_PER_MONTH),
    "meses": timedelta(days=DAYS_PER_MONTH),
    "month": timedelta(days=DAYS_PER_MONTH),
    "months": timedelta(days=DAYS_PER_MONTH),
    "año": timedelta(days=DAYS_PER_YEAR),
    "años": timedelta(days=DAYS_PER_YEAR),
    "year": timedelta(days=DAYS_PER_YEAR),
    "years": timedelta(days=DAYS_PER_YEAR),
}
# «un», «una», «a», «an» = 1 («hace un día», «an hour ago»).
_ONE = frozenset({"un", "una", "a", "an"})
# La unidad acepta la ñ de «años» (``_clean`` quita acentos, no la ñ).
_AGO_ES = re.compile(r"^hace\s+(\d+|un|una)\s*([a-zñ]+)$")
_AGO_EN = re.compile(r"^(\d+|a|an)\s*([a-z]+)\s+ago$")
# «17 nov 2026», «17 de nov. de 2026», «17 de noviembre de 2026» y, sin año,
# «17 nov» o «17 de nov.».
_DAY_MONTH_YEAR = re.compile(r"^(\d{1,2})\s+(?:de\s+)?([a-z]+)\.?(?:,?\s+(?:de\s+)?(\d{4}))?$")
# «Nov 30, 2022» y, sin año, «Nov 30».
_MONTH_DAY_YEAR = re.compile(r"^([a-z]+)\.?\s+(\d{1,2})(?:,?\s+(\d{4}))?$")
_YESTERDAY = frozenset({"ayer", "yesterday"})
_TODAY = frozenset({"hoy", "today"})
_ACCENTS = str.maketrans("áéíóúü", "aeiouu")


def _clean(text: str) -> str:
    return " ".join(text.lower().translate(_ACCENTS).split())


def _relative(text: str, now: datetime) -> datetime | None:
    match = _AGO_ES.match(text) or _AGO_EN.match(text)
    if match is None:
        return None
    amount, unit = match.groups()
    step = _UNITS.get(unit)
    if step is None:
        return None
    count = 1 if amount in _ONE else int(amount)
    return (now - step * count).astimezone(UTC)


def _absolute(text: str, today: date) -> date | None:
    """Una fecha escrita; sin año es la última vez que cayó ese día (``today`` o antes)."""
    day_first = _DAY_MONTH_YEAR.match(text)
    if day_first is not None:
        day, month, year = day_first.groups()
    else:
        month_first = _MONTH_DAY_YEAR.match(text)
        if month_first is None:
            return None
        month, day, year = month_first.groups()
    number = _MONTHS.get(month[:3])
    if number is None:
        return None
    try:
        if year is not None:
            return date(int(year), number, int(day))
        # Google omite el año cuando es el actual; si así queda en el futuro
        # («25 dic» leído en noviembre), es del año anterior.
        found = date(today.year, number, int(day))
        return found if found <= today else found.replace(year=today.year - 1)
    except ValueError:
        return None


def parse_result_date(text: str | None, now: datetime, tz: tzinfo) -> datetime | None:
    """Convierte la fecha en texto de un resultado de Google web.

    Args:
        text: Lo que dio Google: «hace 15 horas», «hace 1 día», «ayer»,
            «hace 3 meses», «hace 2 años», «17 nov 2026», «17 de nov. de
            2026», «17 nov» (sin año), «Nov 30, 2022», «21h ago».
        now: Hora actual con zona (las relativas se cuentan desde aquí).
        tz: Zona en que se leen las fechas sin hora (la de la Ciudad de México).

    Returns:
        La fecha en UTC, o ``None`` si no hay texto, no se entiende o queda en
        el futuro. Nunca se inventa una fecha: los meses cuentan 30 días y
        los años 365, y una fecha sin año es la más reciente que no queda en
        el futuro.

    Example:
        >>> parse_result_date("hace 5 días", datetime(2026, 11, 18, 19, tzinfo=UTC), MEXICO_CITY)
        datetime.datetime(2026, 11, 13, 19, 0, tzinfo=datetime.timezone.utc)
    """
    if not text:
        return None
    clean = _clean(text)
    if clean in _TODAY:
        return now.astimezone(UTC)
    if clean in _YESTERDAY:
        return (now - timedelta(days=1)).astimezone(UTC)
    relative = _relative(clean, now)
    if relative is not None:
        return relative
    today = now.astimezone(tz).date()
    day = _absolute(clean, today)
    if day is None or day > today:
        return None
    return datetime.combine(day, DATE_ONLY_HOUR, tz).astimezone(UTC)


def kept_by_window(
    window: RunWindow,
    published_at: datetime | None,
    providers: Iterable[Provider | str],
    *,
    manual: bool,
) -> bool:
    """Si una nota se queda en el periodo estricto de una búsqueda.

    Con fecha, se queda si cae en la ventana. Sin fecha, solo en una búsqueda
    manual y solo si la trajo un buscador que ya filtró por fecha
    (``trusts_window``): Google web aplica ``time_period`` del lado de Google.
    En las corridas automáticas una nota sin fecha nunca se queda: no se
    sabe si ya salió en la corrida anterior.

    Args:
        window: Periodo estricto (``strict_window``).
        published_at: Fecha de publicación, si se conoce.
        providers: Proveedores que la encontraron.
        manual: ``True`` en una búsqueda manual (sin ``time_window``).

    Returns:
        ``True`` si la nota le toca a la búsqueda.
    """
    if published_at is not None:
        return window.contains(published_at)
    return manual and any(DIALECTS[Provider(p)].trusts_window for p in providers)
