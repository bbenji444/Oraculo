"""Endpoints de reportes y datos de una búsqueda (especificación §13 y §15, ADR-0018).

- ``POST /searches/{id}/report?format=pdf|html``: el reporte. El PDF se
  descarga; el HTML es la vista previa y lo que se imprime desde el
  navegador. La primera vez puede pedirle el resumen ejecutivo a la IA
  (~0.001 USD); las siguientes lo reutilizan.
- ``GET /searches/{id}/export?format=csv|geojson``: las notas como datos.

Routers delgados: toman las piezas que armó la aplicación al arrancar
(``app.state``) y llaman al caso de uso. El PDF se dibuja en un hilo aparte
para no detener a las demás peticiones.

No hace: no decide qué va en el reporte ni cómo se dibuja.
"""

import re
import unicodedata
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.responses import HTMLResponse
from starlette.concurrency import run_in_threadpool

from app.api.errors import ERROR_RESPONSES, error_responses
from app.api.v1.concepts import get_actor
from app.api.v1.searches import SearchId
from app.application.audit import Actor
from app.application.clock import MEXICO_CITY
from app.application.ports.reports import ReportDocumentsPort
from app.application.ports.search_reads import SearchDetail
from app.application.use_cases.reports import BuildReport, ExportSearch, ReportFormat

router = APIRouter(prefix="/searches", tags=["reportes"], responses=ERROR_RESPONSES)

PDF_MEDIA = "application/pdf"
CSV_MEDIA = "text/csv; charset=utf-8"
# RFC 7946 §12: tipo de medio registrado para GeoJSON.
GEOJSON_MEDIA = "application/geo+json"
# Nombre de archivo corto y seguro para cualquier sistema operativo.
MAX_SLUG_CHARS = 60


def get_report_builder(request: Request) -> BuildReport:
    """Caso de uso del reporte creado al arrancar.

    Args:
        request: Petición actual.

    Returns:
        El caso de uso compartido.
    """
    builder: BuildReport = request.app.state.report_builder
    return builder


def get_search_exporter(request: Request) -> ExportSearch:
    """Caso de uso de la exportación creado al arrancar.

    Args:
        request: Petición actual.

    Returns:
        El caso de uso compartido.
    """
    exporter: ExportSearch = request.app.state.search_exporter
    return exporter


def get_report_documents(request: Request) -> ReportDocumentsPort:
    """Plantilla del reporte y exportaciones, cargadas al arrancar.

    Args:
        request: Petición actual.

    Returns:
        El generador de archivos compartido.
    """
    documents: ReportDocumentsPort = request.app.state.report_documents
    return documents


Builder = Annotated[BuildReport, Depends(get_report_builder)]
Exporter = Annotated[ExportSearch, Depends(get_search_exporter)]
Documents = Annotated[ReportDocumentsPort, Depends(get_report_documents)]
CurrentActor = Annotated[Actor, Depends(get_actor)]


def file_name(search: SearchDetail, extension: str) -> str:
    """Nombre del archivo descargado ("reporte-extorsion-jalisco-2026-10-17.pdf").

    Args:
        search: La búsqueda.
        extension: ``pdf``, ``csv`` o ``geojson``.

    Returns:
        Solo letras ASCII minúsculas, números y guiones (la Ñ queda como n),
        con la fecha de la búsqueda en la Ciudad de México.
    """
    words = " ".join([*(c.name for c in search.concepts), search.region_name])
    ascii_words = unicodedata.normalize("NFKD", words).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_words.lower()).strip("-")[:MAX_SLUG_CHARS]
    day = search.created_at.astimezone(MEXICO_CITY).date().isoformat()
    return f"reporte-{slug.rstrip('-')}-{day}.{extension}"


def _download(content: bytes, media_type: str, name: str) -> Response:
    return Response(
        content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )


@router.post(
    "/{search_id}/report",
    response_class=Response,
    summary="Reporte de una búsqueda (PDF o HTML)",
    responses={
        **error_responses(404, 409),
        200: {
            "description": "El reporte: PDF para descargar o HTML para ver e imprimir.",
            "content": {PDF_MEDIA: {}, "text/html": {}},
        },
    },
)
async def search_report(
    builder: Builder,
    documents: Documents,
    actor: CurrentActor,
    search_id: SearchId,
    report_format: Annotated[
        Literal["pdf", "html"], Query(alias="format", description="pdf (descarga) o html.")
    ] = "pdf",
) -> Response:
    """Portada, resumen ejecutivo, mapa, conteo por subregión, notas y fuentes (§15).

    Responde ``409`` si la búsqueda todavía corre. La primera vez le pide el
    resumen ejecutivo a la IA (~0.001 USD; no gasta créditos de SearchApi).
    """
    data = await builder.execute(search_id, ReportFormat(report_format), actor)
    if report_format == "html":
        return HTMLResponse(documents.html(data))
    pdf = await run_in_threadpool(documents.pdf, data)
    return _download(pdf, PDF_MEDIA, file_name(data.search, "pdf"))


@router.get(
    "/{search_id}/export",
    response_class=Response,
    summary="Notas de una búsqueda como datos (CSV o GeoJSON)",
    responses={
        **error_responses(404, 409),
        200: {
            "description": "CSV para Excel o GeoJSON para un SIG.",
            "content": {CSV_MEDIA: {}, GEOJSON_MEDIA: {}},
        },
    },
)
async def export_search(
    exporter: Exporter,
    documents: Documents,
    actor: CurrentActor,
    search_id: SearchId,
    export_format: Annotated[
        Literal["csv", "geojson"], Query(alias="format", description="csv o geojson.")
    ] = "csv",
) -> Response:
    """Notas relevantes con resumen, lugar y link; nunca el texto completo (§8).

    Responde ``409`` si la búsqueda todavía corre. No gasta nada.
    """
    data = await exporter.execute(search_id, ReportFormat(export_format), actor)
    if export_format == "geojson":
        return _download(documents.geojson(data), GEOJSON_MEDIA, file_name(data.search, "geojson"))
    return _download(documents.csv(data), CSV_MEDIA, file_name(data.search, "csv"))
