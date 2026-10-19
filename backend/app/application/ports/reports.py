"""Puertos de los reportes (especificación §15, ADR-0018).

- ``ReportStorePort``: el resumen ejecutivo guardado, el uso de proveedores
  de una búsqueda y la bitácora de reportes generados
  (``app/adapters/persistence/reports_repository.py``).
- ``ReportMapPort``: el mapa estático en SVG, dibujado con PostGIS
  (``app/adapters/reports/static_map.py``).
- ``ReportDocumentsPort``: el reporte en HTML o PDF y las notas en CSV o
  GeoJSON (``app/adapters/reports/render.py``).

No hace: no arma el reporte (eso es ``BuildReport``) ni lo convierte a PDF.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol
from uuid import UUID

from app.application.audit import Actor
from app.domain.aggregates import AggregateLevel
from app.domain.enrichment import LLMUsage
from app.domain.region import Region

if TYPE_CHECKING:
    # Solo para los tipos: el caso de uso importa este módulo al cargarse.
    from app.application.use_cases.reports import ExportData, ReportData


@dataclass(frozen=True, slots=True)
class StoredSummary:
    """El resumen ejecutivo de una búsqueda, ya pagado.

    Attributes:
        text: Párrafos separados por una línea en blanco.
        provider: ``openai`` o ``gemini``.
        model: Modelo que lo escribió.
        prompt_version: Versión del prompt (``summary_v1``).
        usage: Tokens gastados.
        cost_usd: Costo estimado en dólares.
    """

    text: str
    provider: str
    model: str
    prompt_version: str
    usage: LLMUsage
    cost_usd: float


@dataclass(frozen=True, slots=True)
class ProviderUsage:
    """Lo que se le pidió a un proveedor en una búsqueda (pie del reporte).

    Attributes:
        provider: ``searchapi``, ``indice_local``...
        queries: Consultas registradas.
        results: Notas que devolvió (antes de quitar duplicados).
        credits: Créditos gastados.
        from_cache: Consultas respondidas desde la caché (gratis).
        failed: Consultas que fallaron tras los reintentos.
    """

    provider: str
    queries: int
    results: int
    credits: int
    from_cache: int
    failed: int


@dataclass(frozen=True, slots=True)
class SubregionCount:
    """Notas de una subregión, para la tabla y el mapa.

    Attributes:
        code: Clave INEGI.
        name: Nombre para mostrar ("Municipio Zapopan").
        count: Notas relevantes ubicadas ahí.
    """

    code: str
    name: str
    count: int


@dataclass(frozen=True, slots=True)
class MapPoint:
    """Una nota en el mapa estático.

    Attributes:
        lon: Longitud del punto del catálogo.
        lat: Latitud.
        coarse: Si solo se ubicó por estado o país (anillo punteado).
    """

    lon: float
    lat: float
    coarse: bool


class ReportStorePort(Protocol):
    """Lo que el reporte guarda y lee de la base."""

    async def summary(self, search_id: UUID) -> StoredSummary | None:
        """El resumen ejecutivo ya pagado de una búsqueda.

        Args:
            search_id: Búsqueda.

        Returns:
            El resumen, o ``None`` si aún no se ha generado.
        """
        ...

    async def save_summary(self, search_id: UUID, summary: StoredSummary, actor: Actor) -> None:
        """Guarda el resumen (si otro reporte ya lo guardó, se queda el primero).

        Args:
            search_id: Búsqueda.
            summary: Resumen con su costo.
            actor: Quién pidió el reporte.
        """
        ...

    async def provider_usage(self, search_id: UUID) -> list[ProviderUsage]:
        """Consultas, notas y créditos por proveedor de una búsqueda.

        Args:
            search_id: Búsqueda.

        Returns:
            Uno por proveedor consultado, en orden alfabético.
        """
        ...

    async def record_generated(self, search_id: UUID, report_format: str, actor: Actor) -> None:
        """Deja en la bitácora un ``report.generated`` (§16).

        Args:
            search_id: Búsqueda.
            report_format: ``pdf``, ``html``, ``csv`` o ``geojson``.
            actor: Quién lo pidió.
        """
        ...


class ReportMapPort(Protocol):
    """El mapa estático del reporte."""

    async def render(
        self,
        region: Region,
        level: AggregateLevel,
        counts: Sequence[SubregionCount],
        points: Sequence[MapPoint],
    ) -> str:
        """Dibuja la región con sus subregiones coloreadas y los puntos.

        Args:
            region: Región buscada.
            level: Nivel de las subregiones.
            counts: Notas por subregión (las que no aparecen tienen 0).
            points: Notas ubicadas.

        Returns:
            Un elemento ``<svg>`` listo para incrustar en el HTML.
        """
        ...


class ReportDocumentsPort(Protocol):
    """Los archivos que se entregan: reporte y datos."""

    def html(self, data: "ReportData") -> str:
        """El reporte como página HTML (vista previa e "Imprimir").

        Args:
            data: Lo que lleva el reporte.

        Returns:
            El HTML completo.
        """
        ...

    def pdf(self, data: "ReportData") -> bytes:
        """El reporte en PDF. Es lento: quien lo llame debe usar un hilo aparte.

        Args:
            data: Lo que lleva el reporte.

        Returns:
            Los bytes del PDF.
        """
        ...

    def csv(self, data: "ExportData") -> bytes:
        """Las notas en CSV para Excel.

        Args:
            data: Notas de la búsqueda.

        Returns:
            El archivo.
        """
        ...

    def geojson(self, data: "ExportData") -> bytes:
        """Las notas ubicadas como puntos GeoJSON.

        Args:
            data: Notas de la búsqueda.

        Returns:
            El archivo.
        """
        ...
