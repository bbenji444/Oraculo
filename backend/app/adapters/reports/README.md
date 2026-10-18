# adapters/reports/

El reporte de una búsqueda (especificación §15, [ADR-0018](../../../../docs/adr/0018-reportes-pdf-y-datos.md)). Lo que va en el reporte lo decide `BuildReport` (`app/application/use_cases/reports.py`); aquí solo se dibuja.

| Archivo | Qué hace |
|---|---|
| `static_map.py` | Mapa estático en SVG con PostGIS: subregiones coloreadas por número de notas, vecinas en gris y un punto por nota. |
| `render.py` | Llena la plantilla y devuelve HTML (vista previa e "Imprimir") o PDF (WeasyPrint). |
| `exports.py` | Las notas en CSV (UTF-8 con BOM, para Excel) y GeoJSON (un punto por nota ubicada). |
| `templates/report.html.j2` | Plantilla única del reporte. Escapa todo el texto que viene de la web. |
| `templates/report.css` | Estilos de impresión (A4, numeración de páginas) que sirven también en pantalla. |
| `fonts/` | Noto Sans regular y negrita (OFL) con su manifiesto y SHA-256. |

Nunca se reproduce el texto de una nota (§8): solo título, medio, fecha, lugar, resumen generado y link.

Para ver cómo queda sin gastar nada, las pruebas `tests/unit/test_report_render.py` generan un PDF con datos de prueba y comprueban que la Ñ y los acentos se lean bien.
