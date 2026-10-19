# adapters/reports/

El reporte de una búsqueda (especificación §15, [ADR-0018](../../../../docs/adr/0018-reportes-pdf-y-datos.md)). Lo que va en el reporte lo decide `BuildReport` (`app/application/use_cases/reports.py`); aquí solo se dibuja.

| Archivo | Qué hace |
|---|---|
| `static_map.py` | Mapa estático en SVG con PostGIS: subregiones coloreadas por número de notas, vecinas en gris y un punto por nota. |
| `render.py` | Llena la plantilla y devuelve HTML (vista previa e "Imprimir") o PDF (WeasyPrint); también entrega CSV y GeoJSON. |
| `view.py` | Cifras que muestra el reporte, calculadas de los datos sin IA: datos clave, notas por día, medios con más notas y noticias agrupadas y numeradas. |
| `labels.py` | Textos y fechas en español compartidos por el reporte y los datos. |
| `exports.py` | Las notas en CSV (UTF-8 con BOM, para Excel) y GeoJSON (un punto por nota ubicada). |
| `templates/report.html.j2` | Plantilla única: portada (cifras, resumen ejecutivo, datos clave), análisis (mapa, tabla, notas por día, medios), noticias agrupadas y anexo de metodología. Escapa todo el texto que viene de la web. |
| `templates/report.css` | Estilos de impresión (A4, encabezado y pie con número de página) que sirven también en pantalla. Ojo: WeasyPrint no toma `string-set` dentro de un contenedor flex, y las barras con alto en % se dibujan en SVG. |
| `fonts/` | Noto Sans regular y negrita (OFL) con su manifiesto y SHA-256. |

Nunca se reproduce el texto de una nota (§8): solo título, medio, fecha, lugar, resumen generado y link.

Para ver cómo queda sin gastar nada, las pruebas `tests/unit/test_report_render.py` generan un PDF con datos de prueba y comprueban que la Ñ y los acentos se lean bien.
