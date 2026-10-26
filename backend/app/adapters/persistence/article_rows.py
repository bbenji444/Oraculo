"""Cómo se lee una nota de la base para mostrarla (fragmentos SQL y armado).

Lo comparten las notas de una búsqueda (``search_repository``) y las notas de
un caso (``cases_repository``): así Explorar, el reporte y la sección Casos
muestran la misma nota con los mismos campos (``ArticleItem``).

- Las columnas van con alias fijos; la ubicación principal lleva el prefijo
  ``p_`` para no chocar con las de la nota.
- El punto y el nombre del lugar salen del catálogo, nunca de la IA (§11).

No hace: no arma consultas completas ni decide qué notas se piden (eso es
cada repositorio); nunca lee el texto de la nota (CLAUDE.md §8).
"""

from collections.abc import Mapping, Sequence
from typing import Any

from sqlalchemy import RowMapping

from app.application.ports.search_reads import (
    ArticleItem,
    CategoryView,
    JudgementView,
    LocationView,
)
from app.domain.authority import (
    FGR_FEDERAL_EXCLUDED,
    Authority,
    RelevanceRule,
    effective_relevance,
    parse_authority,
)

ARTICLE_COLUMNS = """
    a.id, a.title, a.source_name, a.source_domain, a.url_canonical, a.published_at,
    a.summary, a.event_type, a.event_date, a.extraction_status, a.enrichment_status,
    a.story_id, a.category_raw, a.authority,
    (SELECT json_build_object('id', c.id, 'name', c.name, 'color', c.color, 'symbol', c.symbol)
     FROM categories c WHERE c.id = a.category_id) AS category
"""
LOCATION_COLUMNS = """
    p.mention_text, p.role, p.precision, p.confidence, p.is_primary, r.id AS region_id,
    r.code AS region_code, r.level::text AS region_level, r.name AS region_name,
    r.display_prefix, p.place_name, ST_X(p.point) AS lon, ST_Y(p.point) AS lat
"""
# La ubicación principal, con el prefijo "p_" para no chocar con las de la nota.
# Pide ``LEFT JOIN article_locations p ON p.article_id = a.id AND p.is_primary``
# y ``LEFT JOIN regions r ON r.id = p.region_id``.
PRIMARY_COLUMNS = """
    p.id AS p_id, p.mention_text AS p_mention_text, p.role AS p_role,
    p.precision AS p_precision, p.confidence AS p_confidence, p.is_primary AS p_is_primary,
    r.id AS p_region_id, r.code AS p_region_code, r.level::text AS p_region_level,
    r.name AS p_region_name, r.display_prefix AS p_display_prefix,
    p.place_name AS p_place_name, ST_X(p.point) AS p_lon, ST_Y(p.point) AS p_lat
"""
# Juicios de la IA en todas las búsquedas donde salió la nota, con el nombre
# actual de cada concepto (fuera de una búsqueda concreta). Llevan la regla
# del concepto para aplicar la de «FGR federal» al armarlos (ADR-0030).
ALL_JUDGEMENTS = """
    COALESCE((SELECT json_agg(json_build_array(ac.concept_id, c.name,
        ac.is_relevant, ac.relevance_score, ac.relevance_reason, c.relevance_rule)
        ORDER BY ac.concept_id)
        FROM article_concepts ac JOIN concepts c ON c.id = ac.concept_id
        WHERE ac.article_id = a.id), '[]')
"""
# Condición SQL de la regla «FGR federal» (ADR-0030), para filtrar en la base
# lo mismo que ``effective_relevance``: con ``ac`` (juicio), ``c`` (concepto)
# y ``a`` (nota) a la mano, la nota sigue siendo relevante salvo que el
# concepto pida la FGR federal y la FGR no actúe. Se arma con los valores del
# dominio para que el SQL y Python nunca digan cosas distintas.
_EXCLUDED_SQL = ", ".join(f"'{authority.value}'" for authority in FGR_FEDERAL_EXCLUDED)
KEEPS_RELEVANCE = (
    f"NOT (c.relevance_rule = '{RelevanceRule.FGR_FEDERAL.value}' "
    f"AND a.authority IN ({_EXCLUDED_SQL}))"
)
# Proveedores que la encontraron en cualquier búsqueda.
ALL_PROVIDERS = """
    ARRAY(SELECT DISTINCT provider FROM search_results WHERE article_id = a.id
        ORDER BY provider)
"""


def place_name(
    level: str | None, prefix: str | None, name: str | None, detail: str | None = None
) -> str | None:
    """Nombre del lugar para mostrar, como ``Region.display_name``.

    Args:
        level: Nivel de la región (``municipality``, ``locality``…).
        prefix: Prefijo ("Alcaldía", "Municipio").
        name: Nombre oficial.
        detail: Colonia de OpenStreetMap, si se usó una (ADR-0020).

    Returns:
        "Polanco, Alcaldía Miguel Hidalgo", o ``None`` si no hay región.
    """
    if name is None:
        return None
    region = f"{prefix} {name}" if level in ("municipality", "locality") and prefix else name
    return f"{detail}, {region}" if detail else region


def location_view(row: RowMapping, prefix: str = "") -> LocationView:
    """Una mención de lugar leída con ``LOCATION_COLUMNS`` o ``PRIMARY_COLUMNS``.

    Args:
        row: Fila de la consulta.
        prefix: ``"p_"`` para la ubicación principal; vacío para las demás.

    Returns:
        La ubicación lista para la API.
    """
    return LocationView(
        mention=row[f"{prefix}mention_text"],
        role=row[f"{prefix}role"],
        precision=row[f"{prefix}precision"],
        confidence=float(row[f"{prefix}confidence"]),
        is_primary=row[f"{prefix}is_primary"],
        region_id=row[f"{prefix}region_id"],
        region_code=row[f"{prefix}region_code"],
        place=place_name(
            row[f"{prefix}region_level"],
            row[f"{prefix}display_prefix"],
            row[f"{prefix}region_name"],
            row[f"{prefix}place_name"],
        ),
        lon=row[f"{prefix}lon"],
        lat=row[f"{prefix}lat"],
    )


def article_item(row: RowMapping) -> ArticleItem:
    """Una nota leída con ``ARTICLE_COLUMNS`` y ``PRIMARY_COLUMNS``.

    La fila trae además ``judgements`` (JSON), ``in_region`` y ``providers``.
    La relevancia de cada juicio ya sale con la regla de su concepto aplicada
    (``effective_relevance``, ADR-0030).

    Args:
        row: Fila de la consulta.

    Returns:
        La nota como la muestra Explorar.
    """
    authority = parse_authority(row["authority"])
    return ArticleItem(
        article_id=row["id"],
        title=row["title"],
        source_name=row["source_name"],
        source_domain=row["source_domain"],
        url=row["url_canonical"],
        published_at=row["published_at"],
        summary=row["summary"],
        event_type=row["event_type"],
        event_date=row["event_date"],
        extraction_status=row["extraction_status"],
        enrichment_status=row["enrichment_status"],
        judgements=tuple(judgement_view(j, authority) for j in row["judgements"]),
        primary=location_view(row, "p_") if row["p_id"] is not None else None,
        in_region=row["in_region"],
        providers=tuple(row["providers"]),
        story_id=row["story_id"],
        category=category_view(row["category"]),
        category_raw=row["category_raw"],
        authority=authority,
    )


def judgement_view(value: Sequence[Any], authority: Authority | None) -> JudgementView:
    """Un juicio leído del JSON de los juicios, con la regla de su concepto aplicada.

    Args:
        value: ``[concept_id, nombre, relevante, puntaje, razón, regla]``.
        authority: Quién actúa en la nota.

    Returns:
        El juicio con la relevancia final (ADR-0030).
    """
    concept_id, name, relevant, score, reason, rule = value
    relevant, reason = effective_relevance(relevant, reason, RelevanceRule(rule), authority)
    return JudgementView(concept_id, name, relevant, float(score), reason)


def category_view(value: Mapping[str, Any] | None) -> CategoryView | None:
    """La categoría que trae la columna ``category`` (JSON) de ``ARTICLE_COLUMNS``.

    Args:
        value: ``{id, name, color, symbol}`` o ``None`` si falta clasificar.

    Returns:
        La categoría, o ``None``.
    """
    if not value:
        return None
    return CategoryView(
        int(value["id"]), str(value["name"]), value.get("color"), value.get("symbol")
    )
