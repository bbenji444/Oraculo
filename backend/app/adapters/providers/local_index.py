r"""Proveedor ``indice_local``: busca en las notas que juntó la ingesta (ADR-0013).

Cumple el mismo contrato que los demás proveedores (``NewsProviderPort``),
así que ``ExecuteQueries`` lo trata igual: queda en ``provider_queries`` y
sus notas salen como ``RawArticle``. Las reglas de qué nota responde están
en ``app.domain.local_index``; aquí solo se traducen a SQL.

Palabra completa: se usan los límites de palabra de PostgreSQL (``\m`` y
``\M``). Medido el 16/10/2026 con la base en ``C.UTF-8``: la Ñ cuenta como
letra ("ESPA" no coincide dentro de "ESPAÑA"). Los trigramas de
``text_norm`` y ``body_terms`` aceleran estas expresiones.

Se busca en el título y en las frases del cuerpo (ngramas, ADR-0014); las
exclusiones, solo en el título (ver ``app.domain.local_index``).

No hace: no llama a internet ni gasta créditos; no confirma la ubicación
(eso es F4 con el catálogo INEGI).
"""

import json
import re
from collections.abc import Sequence

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine

from app.application.clock import MEXICO_CITY
from app.application.ports.providers import ProviderResponse
from app.domain.articles import RawArticle
from app.domain.errors import ProviderUnavailableError
from app.domain.local_index import LocalIndexCriteria, criteria_for, for_body
from app.domain.queries import PlannedQuery, Provider

# No hay HTTP: 200 significa "la consulta a la base salió bien", para que el
# registro de provider_queries se lea igual que el de los demás proveedores.
OK_STATUS = 200
# Caracteres especiales de las expresiones regulares de PostgreSQL.
_REGEX_SPECIAL = re.compile(r"([\\.^$*+?()\[\]{}|])")

_SEARCH = text(
    r"""
    SELECT id, source, url, title, snippet, source_name, source_domain,
           published_at, language, gdelt_states
    FROM news_index
    WHERE published_at >= :start AND published_at < :end
      AND (text_norm ~ :keywords OR body_terms ~ :body_keywords)
      AND (CAST(:topic AS text) IS NULL OR text_norm ~ :topic OR body_terms ~ :body_topic)
      AND (CAST(:exclude AS text) IS NULL OR text_norm !~ :exclude)
      AND (
            CAST(:place AS text) IS NULL
         OR ((text_norm ~ :place OR body_terms ~ :body_place)
             AND (CAST(:required AS text) IS NULL
                  OR text_norm ~ :required OR body_terms ~ :body_required))
      )
    ORDER BY published_at DESC, id DESC
    LIMIT :limit
    """
)


def word_pattern(terms: Sequence[str]) -> str | None:
    r"""Expresión de PostgreSQL que encuentra cualquiera de los términos completos.

    Args:
        terms: Términos ya normalizados.

    Returns:
        ``\m(?:HACKEO|ROBO DE DATOS)\M``, o ``None`` si no hay términos.
    """
    if not terms:
        return None
    escaped = "|".join(_REGEX_SPECIAL.sub(r"\\\1", term) for term in terms)
    return rf"\m(?:{escaped})\M"


def _sql_params(criteria: LocalIndexCriteria) -> dict[str, object]:
    return {
        "start": criteria.start,
        "end": criteria.end,
        "keywords": word_pattern(criteria.keywords),
        "body_keywords": word_pattern(for_body(criteria.keywords)),
        # Subdivisión («FGR + Homicidio»): también debe aparecer una de estas.
        "topic": word_pattern(criteria.topic_terms),
        "body_topic": word_pattern(for_body(criteria.topic_terms)),
        "exclude": word_pattern(criteria.exclusions),
        "place": word_pattern(criteria.place_terms),
        "body_place": word_pattern(for_body(criteria.place_terms)),
        "required": word_pattern(criteria.required_terms),
        "body_required": word_pattern(for_body(criteria.required_terms)),
        "limit": criteria.limit,
    }


class LocalIndexProvider:
    """Busca en ``news_index`` con las reglas de ``app.domain.local_index``."""

    def __init__(self, engine: AsyncEngine) -> None:
        """Recibe el engine compartido.

        Args:
            engine: Engine asíncrono de SQLAlchemy (psycopg).
        """
        self._engine = engine

    @property
    def provider(self) -> Provider:
        """Ver ``NewsProviderPort.provider``."""
        return Provider.LOCAL_INDEX

    def is_configured(self) -> bool:
        """Siempre disponible: no necesita llave. Si el índice está vacío, no trae notas."""
        return True

    def request_params(self, query: PlannedQuery) -> dict[str, str]:
        """Criterios en texto, para mostrarlos y registrarlos en ``provider_queries``."""
        criteria = criteria_for(query, MEXICO_CITY)
        return {
            "palabras": " | ".join(criteria.keywords),
            "subdivision": " | ".join(criteria.topic_terms),
            "excluir": " | ".join(criteria.exclusions),
            "lugar": " | ".join(criteria.place_terms),
            "estado_requerido": " | ".join(criteria.required_terms),
            "desde": criteria.start.isoformat(),
            "hasta": criteria.end.isoformat(),
            "max": str(criteria.limit),
        }

    def estimate_cost(self, query: PlannedQuery) -> int:
        """Gratis."""
        return 0

    async def search(self, query: PlannedQuery) -> ProviderResponse:
        """Busca en el índice.

        Args:
            query: Consulta planeada.

        Returns:
            Las notas más recientes que cumplen los criterios.

        Raises:
            ProviderUnavailableError: Si la base no respondió.
        """
        criteria = criteria_for(query, MEXICO_CITY)
        try:
            async with self._engine.connect() as conn:
                rows = (await conn.execute(_SEARCH, _sql_params(criteria))).mappings().all()
        except SQLAlchemyError as error:
            raise ProviderUnavailableError(
                "No se pudo consultar el índice local.",
                provider=Provider.LOCAL_INDEX.value,
                details={"error": type(error).__name__},
            ) from error
        articles = tuple(
            RawArticle.create(
                provider=Provider.LOCAL_INDEX,
                provider_rank=rank,
                url=row["url"],
                title=row["title"],
                source_name=row["source_name"],
                source_domain=row["source_domain"],
                published_at=row["published_at"],
                snippet=row["snippet"],
                language=row["language"],
                raw={
                    "news_index_id": row["id"],
                    "source": row["source"],
                    "gdelt_states": list(row["gdelt_states"]),
                },
            )
            for rank, row in enumerate(rows, start=1)
        )
        body = json.dumps(
            [{"id": row["id"], "url": row["url"]} for row in rows], ensure_ascii=False
        )
        return ProviderResponse(articles, OK_STATUS, self.request_params(query), body)
