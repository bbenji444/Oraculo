"""Notas de una búsqueda en CSV y GeoJSON (especificación §15, ADR-0018).

- **CSV:** una fila por nota relevante, en UTF-8 con BOM para que Excel
  muestre la Ñ y los acentos al abrirlo con doble clic.
- **GeoJSON** (RFC 7946): un punto por nota ubicada, para QGIS o Google
  Earth. Las notas sin ubicación no tienen punto: solo van en el CSV.

Solo llevan metadatos, el resumen generado y el link, nunca el texto de la
nota (§8). Las fechas van en hora de la Ciudad de México.

No hace: no decide qué notas se exportan (eso es ``ExportSearch``).
"""

import csv
import io
import json
from typing import Any

from app.adapters.reports.render import PRECISION_LABEL, PROVIDER_LABEL, mexico_datetime
from app.application.ports.search_reads import ArticleItem
from app.application.use_cases.reports import ExportData

CSV_COLUMNS = (
    "titulo",
    "medio",
    "publicada",
    "lugar",
    "precision",
    "dentro_de_la_region",
    "latitud",
    "longitud",
    "conceptos",
    "resumen_automatico",
    "proveedores",
    "link",
)
# Una celda que empieza así, Excel la toma como fórmula. Los títulos vienen
# de la web: se antepone un apóstrofo para que se lean como texto (OWASP,
# "CSV Injection").
_FORMULA_START = ("=", "+", "-", "@", "\t", "\r")
_IN_REGION = {True: "sí", False: "no", None: "sin ubicación"}


def _safe(value: str) -> str:
    return f"'{value}" if value.startswith(_FORMULA_START) else value


def _fields(article: ArticleItem) -> dict[str, Any]:
    primary = article.primary
    return {
        "titulo": article.title,
        "medio": article.source_name or article.source_domain or "",
        "publicada": mexico_datetime(article.published_at) if article.published_at else "",
        "lugar": (primary.place or "") if primary else "",
        "precision": PRECISION_LABEL[primary.precision if primary else "unknown"],
        "dentro_de_la_region": _IN_REGION[article.in_region],
        "latitud": primary.lat if primary else None,
        "longitud": primary.lon if primary else None,
        "conceptos": ", ".join(j.name for j in article.judgements if j.is_relevant),
        "resumen_automatico": article.summary or "",
        "proveedores": ", ".join(PROVIDER_LABEL.get(p, p) for p in article.providers),
        "link": article.url,
    }


def to_csv(data: ExportData) -> bytes:
    """Las notas en CSV para Excel.

    Args:
        data: Notas de la búsqueda.

    Returns:
        El archivo en UTF-8 con BOM, separado por comas, con encabezados.
    """
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerow(CSV_COLUMNS)
    for article in data.articles:
        fields = _fields(article)
        writer.writerow(
            _safe(v) if isinstance(v, str) else ("" if v is None else v)
            for v in (fields[c] for c in CSV_COLUMNS)
        )
    return buffer.getvalue().encode("utf-8-sig")


def to_geojson(data: ExportData) -> bytes:
    """Las notas ubicadas como puntos GeoJSON.

    Args:
        data: Notas de la búsqueda.

    Returns:
        Un ``FeatureCollection`` en UTF-8, con coordenadas [longitud, latitud].
    """
    features = [
        {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [a.primary.lon, a.primary.lat]},
            "properties": {k: v for k, v in _fields(a).items() if k not in ("latitud", "longitud")},
        }
        for a in data.articles
        if a.primary and a.primary.lon is not None and a.primary.lat is not None
    ]
    collection = {
        "type": "FeatureCollection",
        # Miembros propios (RFC 7946 §6.1): de qué búsqueda salen los puntos.
        "busqueda": {
            "id": str(data.search.search_id),
            "region": data.breadcrumb,
            "conceptos": [c.name for c in data.search.concepts],
            "desde": data.search.date_from.isoformat(),
            "hasta": data.search.date_to.isoformat(),
            "generado": mexico_datetime(data.generated_at),
        },
        "features": features,
    }
    return json.dumps(collection, ensure_ascii=False, indent=2).encode("utf-8")
