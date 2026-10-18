"""Reporte en HTML y PDF desde una sola plantilla (especificación §15, ADR-0018).

``ReportRenderer`` llena ``templates/report.html.j2`` con un ``ReportData``:
- **HTML:** vista previa y versión para imprimir desde el navegador, con el
  CSS incrustado.
- **PDF:** el mismo HTML convertido con WeasyPrint, con la fuente Noto Sans
  incluida en ``fonts/`` para que la Ñ y los acentos salgan iguales en
  cualquier servidor.

Jinja escapa todo el texto (títulos y resúmenes vienen de la web). Lo único
que se inserta tal cual es el SVG del mapa, que arma ``static_map`` con los
nombres ya escapados.

WeasyPrint solo puede leer archivos locales (las fuentes): nunca descarga
nada de internet, aunque una nota traiga links.

No hace: no decide qué va en el reporte (eso es ``BuildReport``) y nunca
muestra el texto completo de una nota (§8): solo título, resumen y link.
"""

from collections.abc import Sequence
from datetime import date, datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup
from weasyprint import CSS, HTML
from weasyprint.text.fonts import FontConfiguration
from weasyprint.urls import URLFetcher

from app.adapters.reports.static_map import legend
from app.application.clock import MEXICO_CITY
from app.application.ports.reports import ProviderUsage
from app.application.use_cases.reports import ReportData
from app.domain.aggregates import AggregateLevel

TEMPLATES_DIR = Path(__file__).parent / "templates"
FONTS_DIR = Path(__file__).parent / "fonts"
TEMPLATE = "report.html.j2"
STYLESHEET = TEMPLATES_DIR / "report.css"

LEVEL_LABEL = {
    AggregateLevel.COUNTRY: "País",
    AggregateLevel.STATE: "Estado",
    AggregateLevel.MUNICIPALITY: "Municipio",
    AggregateLevel.LOCALITY: "Localidad",
}
# Mismas palabras que la leyenda de precisión del globo (§14.4).
PRECISION_LABEL = {
    "locality": "Localidad",
    "municipality": "Municipio",
    "state": "Solo estado",
    "country": "Solo país",
    "unknown": "Sin ubicación",
}
PROVIDER_LABEL = {
    "searchapi": "Google News (SearchApi)",
    "indice_local": "Índice local (GDELT y medios mexicanos)",
    "gdelt": "GDELT",
    "google_news_rss": "Google News RSS",
}
# Proveedores con datos de GDELT: piden citar "The GDELT Project" (§8).
GDELT_PROVIDERS = frozenset({"indice_local", "gdelt"})


def mexico_datetime(value: datetime | None) -> str:
    """Fecha y hora en la Ciudad de México ("16/10/2026 11:38").

    Args:
        value: Momento con zona horaria, o ``None``.

    Returns:
        El texto, o "Sin fecha".
    """
    if value is None:
        return "Sin fecha"
    return value.astimezone(MEXICO_CITY).strftime("%d/%m/%Y %H:%M")


def mexico_date(value: date) -> str:
    """Fecha corta ("16/10/2026").

    Args:
        value: Día.

    Returns:
        El texto.
    """
    return value.strftime("%d/%m/%Y")


def paragraphs(text: str) -> list[str]:
    """Separa un texto en párrafos por las líneas en blanco.

    Args:
        text: Texto del resumen ejecutivo.

    Returns:
        Los párrafos sin espacios sobrantes.
    """
    return [p.strip() for p in text.split("\n\n") if p.strip()]


def _uses_gdelt(providers: Sequence[ProviderUsage]) -> bool:
    return any(p.provider in GDELT_PROVIDERS and p.queries > 0 for p in providers)


class ReportRenderer:
    """Convierte un ``ReportData`` en HTML o PDF."""

    def __init__(self) -> None:
        """Prepara la plantilla una sola vez (se reutiliza en cada reporte)."""
        self._env = Environment(
            loader=FileSystemLoader(TEMPLATES_DIR),
            autoescape=select_autoescape(["html", "j2"]),
            trim_blocks=True,
            lstrip_blocks=True,
        )
        self._env.filters["mx_datetime"] = mexico_datetime
        self._env.filters["mx_date"] = mexico_date
        self._env.filters["paragraphs"] = paragraphs
        self._css = STYLESHEET.read_text(encoding="utf-8")

    def html(self, data: ReportData) -> str:
        """El reporte como página HTML completa, con su CSS incrustado.

        Args:
            data: Lo que lleva el reporte.

        Returns:
            El HTML.
        """
        return self._render(data, inline_css=True)

    def pdf(self, data: ReportData) -> bytes:
        """El reporte en PDF (A4).

        Tarda ~1 s por cada 50 notas: quien lo llame desde código asíncrono
        debe correrlo en un hilo aparte.

        Args:
            data: Lo que lleva el reporte.

        Returns:
            Los bytes del PDF.
        """
        fonts = FontConfiguration()
        # Solo archivos locales: la fuente. Nada de internet.
        fetcher = URLFetcher(allowed_protocols={"file"})
        stylesheet = CSS(
            string=self._css,
            base_url=f"{FONTS_DIR.as_uri()}/",
            font_config=fonts,
            url_fetcher=fetcher,
        )
        document = HTML(
            string=self._render(data, inline_css=False),
            base_url=f"{FONTS_DIR.as_uri()}/",
            url_fetcher=fetcher,
        )
        pdf: bytes = document.write_pdf(stylesheets=[stylesheet], font_config=fonts)
        return pdf

    def _render(self, data: ReportData, *, inline_css: bool) -> str:
        total = len(data.articles)
        inside = sum(c.count for c in data.counts) + data.coarser
        max_count = max((c.count for c in data.counts), default=0)
        return self._env.get_template(TEMPLATE).render(
            data=data,
            css=Markup(self._css) if inline_css else None,  # noqa: S704 — CSS propio del repositorio
            map_svg=Markup(data.map_svg),  # noqa: S704 — SVG de static_map con los textos ya escapados
            legend=legend(max_count),
            level_label=LEVEL_LABEL[data.level],
            precision_label=PRECISION_LABEL,
            provider_label=PROVIDER_LABEL,
            total=total,
            inside=inside,
            uses_gdelt=_uses_gdelt(data.providers),
        )
