"""Lo que se manda de cada corrida FGR (F12.11, ADR-0039).

Implementa ``ReportSourcePort`` para la fuente ``monitor.corrida_fgr``: lee de
PostgreSQL la corrida, su ventana de horas, cuántas notas trajo, los delitos
con más notas y la ruta de su PDF, y arma el asunto y el cuerpo del correo.

El cuerpo es corto a propósito: resumen y PDF adjunto. Nunca reproduce notas
completas (CLAUDE.md §8).

Lee como el sistema (``as_system``): las corridas automáticas son de todos
los que reciben envíos, aunque la búsqueda quede a nombre de quien la lanzó.
Solo toca búsquedas con ``trigger = 'automatic'``; nunca las de una persona
(ADR-0045).

No hace: no genera el PDF (eso es la corrida) ni manda nada.
"""

from html import escape
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.adapters.persistence.access_scope import as_system
from app.application.ports.deliveries import ReportContent
from app.domain.deliveries import SOURCE_FGR_RUN

MEXICO_CITY = ZoneInfo("America/Mexico_City")
# Delitos que se listan en el cuerpo del correo: los que más salen.
TOP_CATEGORIES = 5

_RUN = text(
    """
    SELECT s.id, s.scheduled_for, s.window_start, s.window_end, s.results_count, r.pdf_path
    FROM searches s LEFT JOIN reports r ON r.search_id = s.id
    WHERE s.id = CAST(:id AS uuid) AND s.trigger = 'automatic' AND s.deleted_at IS NULL
    """
)
_CATEGORIES = text(
    """
    SELECT coalesce(c.name, 'Sin clasificar') AS name, count(DISTINCT a.id) AS notes
    FROM search_results sr
    JOIN articles a ON a.id = sr.article_id
    LEFT JOIN categories c ON c.id = a.category_id
    WHERE sr.search_id = CAST(:id AS uuid) AND sr.in_region IS NOT FALSE
    GROUP BY 1 ORDER BY notes DESC, name LIMIT :limit
    """
)
_LATEST = text(
    """
    SELECT s.id FROM searches s JOIN reports r ON r.search_id = s.id
    WHERE s.trigger = 'automatic' AND s.deleted_at IS NULL AND r.pdf_path IS NOT NULL
    ORDER BY s.scheduled_for DESC NULLS LAST LIMIT 1
    """
)


class PostgresRunReports:
    """``ReportSourcePort`` para los reportes de las corridas FGR."""

    def __init__(self, engine: AsyncEngine) -> None:
        """Recibe el motor de la base.

        Args:
            engine: Motor asíncrono de SQLAlchemy.
        """
        self._engine = engine

    async def latest_ref(self, source: str) -> str | None:
        """Ver ``ReportSourcePort.latest_ref``."""
        if source != SOURCE_FGR_RUN:
            return None
        with as_system():
            async with self._engine.connect() as conn:
                row = (await conn.execute(_LATEST)).first()
        return str(row.id) if row else None

    async def content_for(self, source: str, source_ref: str) -> ReportContent | None:
        """Ver ``ReportSourcePort.content_for``."""
        if source != SOURCE_FGR_RUN:
            return None
        with as_system():
            async with self._engine.connect() as conn:
                run = (await conn.execute(_RUN, {"id": source_ref})).first()
                if run is None:
                    return None
                categories = (
                    await conn.execute(_CATEGORIES, {"id": source_ref, "limit": TOP_CATEGORIES})
                ).all()
        slot = run.scheduled_for.astimezone(MEXICO_CITY) if run.scheduled_for else None
        when = slot.strftime("%d/%m/%Y, %H:%M") if slot else "sin hora"
        period = ""
        if run.window_start and run.window_end:
            start = run.window_start.astimezone(MEXICO_CITY).strftime("%H:%M")
            end = run.window_end.astimezone(MEXICO_CITY).strftime("%H:%M")
            period = f"{start} a {end}"
        highlights = tuple(f"{c.name}: {c.notes}" for c in categories)
        pdf = Path(run.pdf_path) if run.pdf_path else None
        title = f"Reporte FGR · corrida de las {slot.strftime('%H:%M') if slot else '—'}"
        return ReportContent(
            source_ref=source_ref,
            title=title,
            subject=f"Reporte FGR · corrida {when} (CDMX)",
            html_body=_body(when, period, run.results_count, highlights, pdf),
            pdf_path=pdf if pdf and pdf.is_file() else None,
            slot_hour=slot.hour if slot else None,
            highlights=highlights,
        )


def _body(
    when: str, period: str, notes: int | None, highlights: tuple[str, ...], pdf: Path | None
) -> str:
    items = "".join(f"<li>{escape(h)}</li>" for h in highlights)
    period_line = f"<li><b>Periodo cubierto:</b> {escape(period)}</li>" if period else ""
    attachment = (
        f"<p>El reporte completo va adjunto: <i>{escape(pdf.name)}</i>.</p>"
        if pdf and pdf.is_file()
        else "<p>El PDF de esta corrida no está disponible; puedes pedirlo desde el monitor.</p>"
    )
    return (
        "<p>Hola,</p>"
        f"<p>Este es el reporte automático del Monitor de Noticias (Oráculo).</p>"
        f"<h3>Corrida automática FGR · {escape(when)} (CDMX)</h3>"
        f"<ul>{period_line}<li><b>Notas encontradas:</b> {notes or 0}</li></ul>"
        + (f"<p><b>Delitos con más notas:</b></p><ol>{items}</ol>" if items else "")
        + attachment
        + "<p>— Envíos automáticos de Oráculo</p>"
    )
