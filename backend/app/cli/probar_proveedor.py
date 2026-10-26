"""Comando ``make probar-proveedor``: UNA consulta real a un proveedor (§17 F3).

Para qué: ver con datos reales cómo responde un proveedor antes de confiar
en su adaptador, y guardar esa respuesta como fixture para las pruebas (que
nunca salen a internet).

Pasos:

1. Arma la consulta con las mismas piezas que una búsqueda real: el concepto
   guardado, la región (por clave INEGI o ISO) y el rango (``build_queries``).
   Con ``--texto`` se puede reemplazar el texto para un experimento puntual.
2. Muestra la consulta exacta, los parámetros, los créditos estimados y los
   créditos ya gastados en el mes; si se pasaría del tope mensual
   (``SEARCHAPI_MONTHLY_CREDIT_LIMIT``) no envía nada. Luego **pide
   escribir "si"** para enviarla. Cualquier otra respuesta cancela.
3. Envía una sola consulta, la registra en ``provider_queries`` y en la
   bitácora, y muestra 5 resultados normalizados.
4. Guarda la respuesta cruda en ``tests/fixtures/providers/`` **sin la
   llave** del proveedor: si la llave aparece en el archivo, no se guarda.

Uso:
    ``make probar-proveedor ARGS="--proveedor gdelt --concepto Ciberseguridad
    --region 09 --dias 7 --nombre cdmx_7d"``

No hace: no usa la caché (siempre consulta de verdad) ni guarda notas.
"""

import argparse
import asyncio
import json
import logging
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime
from pathlib import Path

from sqlalchemy.ext.asyncio import create_async_engine

from app.adapters.persistence.concepts_repository import PostgresConceptRepository
from app.adapters.persistence.provider_queries_repository import PostgresProviderQueryLog
from app.adapters.persistence.regions_repository import PostgresRegionRepository
from app.adapters.providers.browserwork import NOT_CONFIGURED_MESSAGE as BROWSERWORK_NOT_CONFIGURED
from app.adapters.providers.factory import build_provider
from app.adapters.providers.gdelt import DISABLED_MESSAGE as GDELT_DISABLED_MESSAGE
from app.adapters.providers.google_news_rss import DISABLED_MESSAGE
from app.application.audit import Actor
from app.application.clock import MEXICO_CITY, mexico_city_today
from app.application.ports.concepts import ConceptRepositoryPort
from app.application.ports.provider_log import ProviderQueryLogPort, ProviderQueryRecord
from app.application.ports.providers import NewsProviderPort, ProviderResponse
from app.application.ports.regions import RegionRepositoryPort
from app.core.config import Settings, get_settings
from app.domain.budget import MonthlyCredits, month_start
from app.domain.concept import Concept
from app.domain.errors import ProviderError
from app.domain.names import normalize_name
from app.domain.queries import DateWindow, PlannedQuery, Provider, place_for
from app.domain.query_builder import build_queries
from app.geodata.consola import configure_cli_logging, heading

logger = logging.getLogger(__name__)

FIXTURES_DIR = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "providers"
# Respuesta que confirma el envío: hay que escribirla completa.
CONFIRMATION = "si"
# Ejemplos que se muestran (CLAUDE.md §2.6: 5 ejemplos reales).
EXAMPLES = 5
REDACTED = "REDACTADO"
_EXTENSION = {
    Provider.SEARCHAPI: "json",
    Provider.GDELT: "json",
    Provider.GOOGLE_NEWS_RSS: "xml",
    Provider.BROWSERWORK_BING: "json",
    Provider.BROWSERWORK_GOOGLE2: "json",
}
_MS_PER_SECOND = 1000
# Por qué un proveedor no se puede consultar.
NOT_CONFIGURED = {
    Provider.SEARCHAPI: "SearchApi no está configurado: falta SEARCHAPI_API_KEY en .env.",
    Provider.GOOGLE_NEWS_RSS: DISABLED_MESSAGE,
    Provider.GDELT: GDELT_DISABLED_MESSAGE,
    # El índice local siempre está disponible; se deja por completitud.
    Provider.LOCAL_INDEX: "El índice local no está disponible.",
    Provider.BROWSERWORK_BING: BROWSERWORK_NOT_CONFIGURED,
    Provider.BROWSERWORK_GOOGLE2: BROWSERWORK_NOT_CONFIGURED,
}


class LeakedSecretError(RuntimeError):
    """La llave del proveedor aparece en la respuesta: no se guarda el fixture."""


@dataclass(frozen=True, slots=True)
class Plan:
    """Consulta lista para mostrar y, si se confirma, enviar.

    Attributes:
        concept: Concepto usado.
        breadcrumb: Región elegida ("México › Ciudad de México").
        query: Consulta exacta.
        params: Parámetros HTTP (sin la llave).
        credits: Créditos estimados.
    """

    concept: Concept
    breadcrumb: str
    query: PlannedQuery
    params: dict[str, str]
    credits: int


async def find_concept(concepts: ConceptRepositoryPort, name: str) -> Concept:
    """Busca un concepto vigente por nombre (sin importar mayúsculas ni acentos).

    Args:
        concepts: Repositorio de conceptos.
        name: Nombre escrito por la persona.

    Returns:
        El concepto.

    Raises:
        SystemExit: Si no existe (con un mensaje para corregir el comando).
    """
    wanted = normalize_name(name)
    for concept in await concepts.list_concepts(None, None, 200):
        if concept.data.name_norm == wanted:
            return concept
    raise SystemExit(f'No existe el concepto "{name}". Revisa la pestaña Conceptos.')


async def build_plan(  # noqa: PLR0913 — refleja las opciones del comando, todo por nombre (*)
    *,
    provider: NewsProviderPort,
    concepts: ConceptRepositoryPort,
    regions: RegionRepositoryPort,
    concept_name: str,
    region_code: str,
    window: DateWindow,
    index: int = 0,
    text: str | None = None,
) -> Plan:
    """Arma la consulta como lo haría una búsqueda real.

    Args:
        provider: Adaptador del proveedor.
        concepts: Repositorio de conceptos.
        regions: Repositorio de regiones.
        concept_name: Nombre del concepto.
        region_code: Clave INEGI o ISO-A3 de la región.
        window: Rango de fechas.
        index: Cuál consulta usar si el concepto se partió en varias.
        text: Texto que reemplaza al generado (experimentos puntuales).

    Returns:
        El plan para mostrar y confirmar.

    Raises:
        SystemExit: Si la región o el índice no existen.
    """
    concept = await find_concept(concepts, concept_name)
    region = await regions.get_by_code(region_code)
    facts = await regions.place_facts(region.id) if region else None
    if region is None or facts is None:
        raise SystemExit(f"No existe una región con clave {region_code}.")
    ancestors = await regions.ancestors(region.id)
    queries = build_queries(concept, place_for(facts), window, [provider.provider])
    if not 0 <= index < len(queries):
        raise SystemExit(f"Solo hay {len(queries)} consulta(s) para este concepto.")
    query = queries[index]
    if text is not None:
        query = replace(query, text=text)
    breadcrumb = " › ".join([*(a.name for a in ancestors), region.name])
    return Plan(
        concept=concept,
        breadcrumb=breadcrumb,
        query=query,
        params=provider.request_params(query),
        credits=provider.estimate_cost(query),
    )


def show_plan(plan: Plan) -> None:
    """Muestra lo que se enviaría.

    Args:
        plan: Plan armado.
    """
    heading(logger, f"Consulta a {plan.query.provider.value} (no se ha enviado nada)")
    logger.info(f"Concepto: {plan.concept.data.name} · Región: {plan.breadcrumb}")
    logger.info(f"Rango: {plan.query.window.describe()}")
    logger.info(f"Texto exacto: {plan.query.text}")
    logger.info(f"Parámetros: {json.dumps(plan.params, ensure_ascii=False)}")
    logger.info(f"Créditos estimados: {plan.credits}")


def confirmed(ask: Callable[[str], str]) -> bool:
    """Pide confirmación explícita.

    Args:
        ask: Función que muestra la pregunta y devuelve la respuesta.

    Returns:
        ``True`` solo si la respuesta es exactamente "si" (sin importar
        mayúsculas ni espacios alrededor).
    """
    return (
        ask(f'Escribe "{CONFIRMATION}" para enviar la consulta: ').strip().lower() == CONFIRMATION
    )


def redact(body: str, secret: str | None) -> str:
    """Quita la llave del texto de la respuesta.

    Args:
        body: Respuesta cruda.
        secret: Llave del proveedor, si tiene.

    Returns:
        El texto con la llave reemplazada por "REDACTADO".
    """
    return body.replace(secret, REDACTED) if secret else body


def save_fixture(  # noqa: PLR0913 — datos del fixture y su destino, todo por nombre (*)
    *,
    provider: Provider,
    name: str,
    response: ProviderResponse,
    query: PlannedQuery,
    secret: str | None,
    directory: Path = FIXTURES_DIR,
) -> Path:
    """Guarda la respuesta cruda y sus datos, sin la llave.

    Args:
        provider: Proveedor.
        name: Nombre corto del fixture (``cdmx_7d``).
        response: Respuesta del proveedor.
        query: Consulta enviada.
        secret: Llave del proveedor, para quitarla.
        directory: Carpeta destino.

    Returns:
        La ruta del archivo con la respuesta.

    Raises:
        LeakedSecretError: Si la llave sigue apareciendo después de quitarla.
    """
    directory.mkdir(parents=True, exist_ok=True)
    stem = f"{provider.value}_{name}"
    body = redact(response.body, secret)
    meta = redact(
        json.dumps(
            {
                "proveedor": provider.value,
                "texto": query.text,
                "parametros": dict(response.params),
                "http_status": response.http_status,
                "grabado": datetime.now(UTC).isoformat(timespec="seconds"),
            },
            ensure_ascii=False,
            indent=2,
        ),
        secret,
    )
    if secret and (secret in body or secret in meta):  # pragma: no cover — defensa extra
        raise LeakedSecretError("La llave aparece en la respuesta; no se guardó el fixture.")
    path = directory / f"{stem}.{_EXTENSION[provider]}"
    path.write_text(body, encoding="utf-8")
    (directory / f"{stem}.meta.json").write_text(meta + "\n", encoding="utf-8")
    return path


def show_examples(response: ProviderResponse) -> None:
    """Muestra los primeros resultados normalizados.

    Args:
        response: Respuesta del proveedor.
    """
    heading(
        logger,
        f"HTTP {response.http_status} · {len(response.articles)} notas normalizadas · "
        f"{response.discarded} descartadas",
    )
    for article in response.articles[:EXAMPLES]:
        when = (
            article.published_at.astimezone(MEXICO_CITY).strftime("%d/%m/%Y %H:%M")
            if article.published_at
            else "sin fecha"
        )
        logger.info(
            f"#{article.provider_rank} [{when}] {article.source_name or article.source_domain} — "
            f"{article.title}\n      {article.url}"
        )


async def execute(
    *,
    provider: NewsProviderPort,
    plan: Plan,
    log: ProviderQueryLogPort,
    actor: Actor,
) -> ProviderResponse | None:
    """Envía la consulta y la registra (también si falla).

    Args:
        provider: Adaptador.
        plan: Plan confirmado.
        log: Registro de peticiones.
        actor: Quién la pidió (para la bitácora).

    Returns:
        La respuesta, o ``None`` si el proveedor falló (el error se muestra).
    """
    started = time.perf_counter()
    try:
        response = await provider.search(plan.query)
    except ProviderError as error:
        await log.record(
            ProviderQueryRecord(
                provider=plan.query.provider.value,
                query_text=plan.query.text,
                params=plan.params,
                status="error",
                http_status=error.http_status,
                duration_ms=int((time.perf_counter() - started) * _MS_PER_SECOND),
                error_message=error.message,
            ),
            actor,
        )
        logger.error(f"{error.message}")
        return None
    await log.record(
        ProviderQueryRecord(
            provider=plan.query.provider.value,
            query_text=plan.query.text,
            params=response.params,
            status="ok",
            http_status=response.http_status,
            results_count=len(response.articles),
            cost_credits=plan.credits,
            duration_ms=int((time.perf_counter() - started) * _MS_PER_SECOND),
        ),
        actor,
    )
    return response


def parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    """Lee las opciones del comando.

    Args:
        argv: Argumentos (por defecto, los de la línea de comandos).

    Returns:
        Las opciones.
    """
    parser = argparse.ArgumentParser(description="Ejecuta UNA consulta real a un proveedor.")
    parser.add_argument("--proveedor", required=True, choices=[p.value for p in Provider])
    parser.add_argument("--concepto", default="Ciberseguridad")
    parser.add_argument("--region", default="09", help="clave INEGI o ISO-A3 (09, 14, COL)")
    parser.add_argument("--dias", type=int, default=7)
    parser.add_argument("--desde", type=date.fromisoformat, help="rango fijo: AAAA-MM-DD")
    parser.add_argument("--hasta", type=date.fromisoformat, help="rango fijo: AAAA-MM-DD")
    parser.add_argument("--indice", type=int, default=0, help="consulta a usar si se partió")
    parser.add_argument("--texto", help="reemplaza el texto generado (experimentos)")
    parser.add_argument("--nombre", required=True, help="nombre corto del fixture, p. ej. cdmx_7d")
    return parser.parse_args(argv)


def window_from(args: argparse.Namespace) -> DateWindow:
    """Rango de fechas según las opciones.

    Args:
        args: Opciones del comando.

    Returns:
        Rango fijo si se dieron ``--desde`` y ``--hasta``; si no, los últimos días.
    """
    if args.desde and args.hasta:
        return DateWindow.between(args.desde, args.hasta)
    return DateWindow.last_days(args.dias, mexico_city_today())


async def run(args: argparse.Namespace, settings: Settings, ask: Callable[[str], str]) -> int:
    """Flujo completo del comando.

    Args:
        args: Opciones.
        settings: Configuración.
        ask: Función para pedir confirmación.

    Returns:
        Código de salida: 0 bien, 1 cancelado o con error.
    """
    engine = create_async_engine(settings.database_url())
    try:
        provider = build_provider(Provider(args.proveedor), settings, engine)
        if not provider.is_configured():
            logger.error(NOT_CONFIGURED[provider.provider])
            return 1
        plan = await build_plan(
            provider=provider,
            concepts=PostgresConceptRepository(engine),
            regions=PostgresRegionRepository(engine),
            concept_name=args.concepto,
            region_code=args.region,
            window=window_from(args),
            index=args.indice,
            text=args.texto,
        )
        show_plan(plan)
        log = PostgresProviderQueryLog(engine)
        if plan.credits:
            used = await log.credits_used_since(
                plan.query.provider.value, month_start(datetime.now(UTC), MEXICO_CITY)
            )
            limit = settings.searchapi_monthly_credit_limit
            logger.info(f"Créditos de este mes: {used} de {limit}")
            if not MonthlyCredits(used=used, limit=limit).try_reserve(plan.credits):
                logger.error("Se alcanzaría el tope mensual de créditos: no se envió nada.")
                return 1
        if not confirmed(ask):
            logger.warning("Cancelado: no se envió nada.")
            return 1
        response = await execute(
            provider=provider,
            plan=plan,
            log=log,
            actor=Actor(settings.dev_user),
        )
        if response is None:
            return 1
        secret = (
            settings.searchapi_api_key.get_secret_value() if settings.searchapi_api_key else None
        )
        path = save_fixture(
            provider=plan.query.provider,
            name=args.nombre,
            response=response,
            query=plan.query,
            secret=secret,
        )
        show_examples(response)
        logger.info(f"Respuesta guardada (sin llave) en {path.name}")
        return 0
    finally:
        await engine.dispose()


def main(argv: Sequence[str] | None = None) -> None:
    """Punto de entrada de la línea de comandos.

    Args:
        argv: Argumentos (por defecto, los de la línea de comandos).
    """
    args = parse_args(argv)
    configure_cli_logging()
    raise SystemExit(asyncio.run(run(args, get_settings(), input)))


if __name__ == "__main__":
    main()
