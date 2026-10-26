"""``ReportDocumentsPort``: reporte en HTML y PDF y datos en CSV y GeoJSON (§15, ADR-0018).

``ReportRenderer`` llena ``templates/report.html.j2`` con un ``ReportData``
(los datos los arma ``exports.py``):
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

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup
from weasyprint import CSS, HTML
from weasyprint.text.fonts import FontConfiguration
from weasyprint.urls import URLFetcher

from app.adapters.reports.exports import to_csv, to_geojson
from app.adapters.reports.labels import (
    PRECISION_LABEL,
    PROVIDER_LABEL,
    mexico_date,
    mexico_datetime,
    mexico_time,
    provider_name,
)
from app.adapters.reports.oraculo import clean
from app.adapters.reports.view import build_view
from app.application.use_cases.reports import ExportData, ReportData

TEMPLATES_DIR = Path(__file__).parent / "templates"
FONTS_DIR = Path(__file__).parent / "fonts"
TEMPLATE = "report.html.j2"
STYLESHEET = TEMPLATES_DIR / "report.css"


def paragraphs(text: str) -> list[str]:
    """Separa un texto en párrafos por las líneas en blanco.

    Args:
        text: Texto del resumen ejecutivo.

    Returns:
        Los párrafos sin espacios sobrantes.
    """
    return [p.strip() for p in text.split("\n\n") if p.strip()]


class ReportRenderer:
    """Convierte un ``ReportData`` en HTML o PDF, y un ``ExportData`` en CSV o GeoJSON."""

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
        self._env.filters["mx_time"] = mexico_time
        self._env.filters["provider_name"] = provider_name
        self._env.filters["paragraphs"] = paragraphs
        # Sin emojis: la fuente del PDF no los tiene y salían como cuadros (F12.10).
        self._env.filters["clean"] = clean
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

    def csv(self, data: ExportData) -> bytes:
        """Ver ``ReportDocumentsPort.csv``."""
        return to_csv(data)

    def geojson(self, data: ExportData) -> bytes:
        """Ver ``ReportDocumentsPort.geojson``."""
        return to_geojson(data)

    def _render(self, data: ReportData, *, inline_css: bool) -> str:
        view = build_view(data)
        return self._env.get_template(TEMPLATE).render(
            data=data,
            view=view,
            css=Markup(self._css) if inline_css else None,  # noqa: S704 — CSS propio del repositorio
            map_svg=Markup(data.map_svg),  # noqa: S704 — SVG de static_map con los textos ya escapados
            # Red de la portada: SVG armado aquí solo con números (oraculo.network_svg).
            network_svg=Markup(view.oraculo.network),  # noqa: S704 — sin texto externo
            precision_label=PRECISION_LABEL,
            provider_label=PROVIDER_LABEL,
        )
