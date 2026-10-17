"""Esquemas de ``/api/v1/local-index`` (pestaña temporal "Notas", ADR-0014).

No hace: no expone las frases del cuerpo (``body_terms``): son solo para
buscar y nunca se muestran (CLAUDE.md §8).
"""

from datetime import date, datetime

from pydantic import BaseModel, Field

from app.application.ports.local_index import IndexStats
from app.application.use_cases.local_index import LocalIndexSearch


class NoteOut(BaseModel):
    """Una nota del índice: metadatos y link, nunca el artículo."""

    title: str
    url: str
    source_domain: str | None
    published_at: datetime | None
    snippet: str | None
    source: str = Field(description="gdelt_ngrams, gdelt_gkg o rss:<medio>.")
    gdelt_states: list[str] = Field(description="Pistas de estado de GDELT (claves INEGI).")


class CountOut(BaseModel):
    """Un conteo con su etiqueta."""

    label: str
    count: int


class LocalIndexSearchOut(BaseModel):
    """Notas del índice local para un concepto, una región y un rango."""

    concept_name: str
    region: str = Field(examples=["México › Ciudad de México › Iztapalapa"])
    period: str = Field(examples=["últimos 7 días"])
    query_text: str = Field(description="La consulta, escrita en palabras.")
    status: str = Field(description="ok, skipped o error.")
    message: str | None
    total: int
    notes: list[NoteOut]
    by_day: list[CountOut]
    by_source: list[CountOut]

    @classmethod
    def from_result(cls, result: LocalIndexSearch) -> "LocalIndexSearchOut":
        """Convierte el resultado del caso de uso.

        Args:
            result: Resultado de ``SearchLocalIndex``.

        Returns:
            El esquema listo para serializar.
        """
        preview, outcome = result.preview, result.outcome
        notes = [
            NoteOut(
                title=a.title,
                url=a.url,
                source_domain=a.source_domain,
                published_at=a.published_at,
                snippet=a.snippet,
                source=str(a.raw.get("source", "")),
                gdelt_states=[str(s) for s in _as_list(a.raw.get("gdelt_states"))],
            )
            for a in outcome.articles
        ]
        return cls(
            concept_name=preview.concept_name,
            region=preview.region.breadcrumb,
            period=preview.window.describe(),
            query_text=outcome.query.text,
            status=outcome.status,
            message=outcome.message,
            total=len(notes),
            notes=notes,
            by_day=[CountOut(label=_day(d), count=n) for d, n in result.by_day],
            by_source=[CountOut(label=s, count=n) for s, n in result.by_source],
        )


def _as_list(value: object) -> list[object]:
    return list(value) if isinstance(value, list | tuple) else []


def _day(value: date) -> str:
    return value.strftime("%d/%m")


class SourceStatsOut(BaseModel):
    """Una fuente del índice."""

    source: str
    notes: int
    with_body: int
    body_mb: float
    oldest: datetime | None
    newest: datetime | None


class IndexStatsOut(BaseModel):
    """Resumen del índice local."""

    sources: list[SourceStatsOut]
    total_notes: int
    total_mb: float
    last_run_at: datetime | None

    @classmethod
    def from_stats(cls, stats: IndexStats) -> "IndexStatsOut":
        """Convierte el resumen del puerto.

        Args:
            stats: Resumen del índice.

        Returns:
            El esquema listo para serializar, con tamaños en MB.
        """
        return cls(
            sources=[
                SourceStatsOut(
                    source=s.source,
                    notes=s.notes,
                    with_body=s.with_body,
                    body_mb=round(s.body_bytes / _BYTES_PER_MB, 1),
                    oldest=s.oldest,
                    newest=s.newest,
                )
                for s in stats.sources
            ],
            total_notes=sum(s.notes for s in stats.sources),
            total_mb=round(stats.total_bytes / _BYTES_PER_MB, 1),
            last_run_at=stats.last_run_at,
        )


_BYTES_PER_MB = 1024 * 1024
