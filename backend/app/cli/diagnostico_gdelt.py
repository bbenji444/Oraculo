"""Comando ``make gdelt-diagnostico``: reintento diario de la consulta D1 (ADR-0012).

GDELT está desactivado (``GDELT_ENABLED=false``) porque respondió 429 de
forma persistente. Criterio aprobado por Benji para proponer reactivarlo:

- Se reintenta **solo D1** (``gobierno sourcelang:spanish``, último día),
  **una vez al día** (hora de la Ciudad de México). Si ya se corrió hoy, no
  se envía nada.
- Se propone reactivar cuando D1 responda **con notas reales en 2 días
  distintos**. En ese momento se avisa a Benji y él decide; este comando
  nunca cambia ``GDELT_ENABLED``.

No pide confirmación: D1 es gratuita y Benji aprobó este reintento diario.
Cada envío queda en ``provider_queries`` y en la bitácora (usuario
``diagnostico-gdelt``). Si D1 trae notas, la respuesta se guarda como fixture:
sería la primera evidencia real del formato de un artículo de GDELT.

Uso: ``make gdelt-diagnostico``

No hace: no activa GDELT ni prueba otras consultas.
"""

import argparse
import asyncio
import logging
import time
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

from sqlalchemy.ext.asyncio import create_async_engine

from app.adapters.persistence.provider_queries_repository import PostgresProviderQueryLog
from app.adapters.providers.factory import build_gdelt
from app.application.audit import Actor
from app.application.clock import MEXICO_CITY, mexico_city_today
from app.application.ports.provider_log import ProviderQueryRecord, QueryRun
from app.application.ports.providers import NewsProviderPort, ProviderResponse
from app.cli.probar_proveedor import save_fixture
from app.core.config import get_settings
from app.domain.errors import ProviderError
from app.domain.queries import CountryFilter, DateWindow, PlannedQuery, Provider
from app.geodata.consola import configure_cli_logging, heading

logger = logging.getLogger(__name__)

# Consulta D1 del diagnóstico del 16/10/2026 (ADR-0012): un término general en
# español, sin filtro de país, en el último día. Siempre debería tener notas.
D1_TEXT = "gobierno sourcelang:spanish"
D1_DAYS = 1
# Criterio de Benji: notas reales en 2 días distintos.
DAYS_REQUIRED = 2
ACTOR = Actor("diagnostico-gdelt")
_MS_PER_SECOND = 1000
# GDELT no usa país en los parámetros (va en el texto); D1 no filtra país.
_NO_COUNTRY = CountryFilter("Sin filtro", None, None, "")


@dataclass(frozen=True, slots=True)
class Status:
    """Cómo va el criterio de reactivación.

    Attributes:
        ran_today: Si D1 ya se envió hoy.
        good_days: Días distintos en que D1 trajo notas.
        criterion_met: Si ya se cumple el criterio (2 días).
    """

    ran_today: bool
    good_days: tuple[date, ...]
    criterion_met: bool


def status_from(runs: Sequence[QueryRun], today: date) -> Status:
    """Calcula el criterio a partir de los envíos registrados de D1.

    Args:
        runs: Envíos de D1 (de ``ProviderQueryLogPort.runs_of``).
        today: Hoy en la Ciudad de México.

    Returns:
        Si ya se corrió hoy y los días con notas reales.
    """

    def local_day(run: QueryRun) -> date:
        return run.created_at.astimezone(MEXICO_CITY).date()

    good = sorted({local_day(r) for r in runs if r.status == "ok" and r.results_count > 0})
    return Status(
        ran_today=any(local_day(r) == today for r in runs),
        good_days=tuple(good),
        criterion_met=len(good) >= DAYS_REQUIRED,
    )


def d1_query(today: date) -> PlannedQuery:
    """La consulta D1 tal como se envió en el diagnóstico.

    Args:
        today: Hoy en la Ciudad de México.

    Returns:
        La consulta planeada.
    """
    return PlannedQuery(
        provider=Provider.GDELT,
        text=D1_TEXT,
        keywords=("gobierno",),
        country=_NO_COUNTRY,
        language="es",
        window=DateWindow.last_days(D1_DAYS, today),
        estimated_credits=0,
    )


async def send_d1(
    provider: NewsProviderPort, query: PlannedQuery, log: PostgresProviderQueryLog
) -> ProviderResponse | None:
    """Envía D1 y la registra (también si falla).

    Args:
        provider: Adaptador de GDELT habilitado solo para esto.
        query: Consulta D1.
        log: Registro de peticiones.

    Returns:
        La respuesta, o ``None`` si falló.
    """
    started = time.perf_counter()
    try:
        response = await provider.search(query)
    except ProviderError as error:
        await log.record(
            ProviderQueryRecord(
                provider=Provider.GDELT.value,
                query_text=query.text,
                params=provider.request_params(query),
                status="error",
                http_status=error.http_status,
                duration_ms=int((time.perf_counter() - started) * _MS_PER_SECOND),
                error_message=error.message,
            ),
            ACTOR,
        )
        logger.warning(error.message)
        return None
    await log.record(
        ProviderQueryRecord(
            provider=Provider.GDELT.value,
            query_text=query.text,
            params=response.params,
            status="ok",
            http_status=response.http_status,
            results_count=len(response.articles),
            duration_ms=int((time.perf_counter() - started) * _MS_PER_SECOND),
        ),
        ACTOR,
    )
    return response


def report(status: Status) -> None:
    """Muestra cómo va el criterio de reactivación.

    Args:
        status: Estado calculado después del envío.
    """
    days = ", ".join(d.strftime("%d/%m/%Y") for d in status.good_days) or "ninguno"
    logger.info(f"Días con notas reales: {len(status.good_days)} de {DAYS_REQUIRED} ({days})")
    if status.criterion_met:
        logger.warning(
            "Se cumple el criterio: proponer a Benji reactivar GDELT (él decide; "
            "GDELT_ENABLED no se cambia solo)."
        )


async def run() -> int:
    """Flujo del comando.

    Returns:
        Código de salida: 0 siempre que el diagnóstico se haya registrado.
    """
    settings = get_settings()
    today = mexico_city_today()
    engine = create_async_engine(settings.database_url())
    log = PostgresProviderQueryLog(engine)
    try:
        heading(logger, f"Diagnóstico diario de GDELT · D1: {D1_TEXT} (último día)")
        before = status_from(await log.runs_of(Provider.GDELT.value, D1_TEXT), today)
        if before.ran_today:
            logger.info("D1 ya se envió hoy: no se envía de nuevo (máximo una vez al día).")
            report(before)
            return 0
        query = d1_query(today)
        response = await send_d1(build_gdelt(settings, enabled=True), query, log)
        if response is not None:
            logger.info(f"HTTP {response.http_status} · {len(response.articles)} notas")
            if response.articles:
                path = save_fixture(
                    provider=Provider.GDELT,
                    name=f"diag_d1_{today.strftime('%Y%m%d')}",
                    response=response,
                    query=query,
                    secret=None,
                )
                logger.info(f"Primera evidencia con notas guardada en {path.name}")
        report(status_from(await log.runs_of(Provider.GDELT.value, D1_TEXT), today))
        return 0
    finally:
        await engine.dispose()


def main(argv: Sequence[str] | None = None) -> None:
    """Punto de entrada de la línea de comandos.

    Args:
        argv: Argumentos (por defecto, los de la línea de comandos).
    """
    argparse.ArgumentParser(description="Reintento diario de D1 en GDELT (ADR-0012).").parse_args(
        argv
    )
    configure_cli_logging()
    raise SystemExit(asyncio.run(run()))


if __name__ == "__main__":
    main()
