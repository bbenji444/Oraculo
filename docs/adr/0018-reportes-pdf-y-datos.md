# ADR-0018 — Reportes en PDF, mapa dibujado en el servidor y datos en CSV y GeoJSON

- **Estado:** aceptado
- **Fecha:** 2026-10-17
- **Fase:** F7
- **Decide:** Benji
- **Complementa:** especificación §15 (reportes) y §8 (nunca reproducir el artículo completo)

## Contexto

La historia H5 pide que, con los resultados de una búsqueda en pantalla, se presione "Generar reporte" y se obtenga un PDF con:
- portada;
- resumen ejecutivo;
- conteo por subregión;
- mapa estático;
- lista de noticias;
- pie con proveedores y créditos.

La especificación ya fijaba Jinja2 y WeasyPrint. Dejaba abierto cómo hacer el mapa: una imagen generada en el servidor o una captura del lienzo del navegador.

El panel de Descargas de la Fase 6 también tiene un botón de datos para quien quiera trabajar las notas en Excel o en un SIG.

## Decisión

1. **Una plantilla, dos salidas.** Hay una sola plantilla Jinja2 (con autoescape). La vista HTML sirve como vista previa y para imprimir; el PDF sale de WeasyPrint 70.0 con CSS de impresión: A4, numeración de páginas y encabezado.
2. **Mapa dibujado en el servidor, en SVG** (decisión de Benji):
   - PostGIS devuelve las subregiones simplificadas (`ST_SimplifyPreserveTopology` + `ST_AsSVG`), coloreadas según cuántas notas tiene cada una, más los puntos de las notas.
   - Lo ubicado solo por estado o país lleva anillo punteado, igual que en el globo.
   - Funciona igual cuando otro sistema (n8n, el sistema principal) pide el reporte por API, sin navegador. No usa librerías de mapas.
3. **Conteo por subregión:**
   - región país → por estado;
   - región estado → por municipio;
   - región municipio o localidad → por localidad.
   - Las notas menos precisas que ese nivel se cuentan aparte, sin repartirlas, como en el mapa de calor (§13).
4. **Resumen ejecutivo con la IA:**
   - Se arma solo con los resúmenes ya generados de las notas relevantes, nunca con el texto de las notas.
   - Es una llamada por búsqueda, con el prompt versionado `summary_v1.md`. El resultado se guarda en la tabla `reports`: regenerar el reporte no vuelve a pagar.
   - En el PDF va marcado como "Resumen automático". Si la IA falla, el reporte sale igual, con un aviso en su lugar.
5. **Fuente incluida:** Noto Sans regular y negrita en versión fija (no variable), con licencia SIL OFL 1.1, desde el repositorio oficial de Noto. Así la Ñ y los acentos salen iguales en cualquier servidor. Los archivos y su SHA-256 quedan en el manifiesto de la carpeta de fuentes.
6. **Datos para descargar** (decisión de Benji):
   - **CSV** en UTF-8 con BOM, para que Excel muestre la Ñ sin pasos extra.
   - **GeoJSON** con un punto por nota ubicada.
   - Los dos llevan solo metadatos, resumen generado y link (§8), con las fechas en hora de la Ciudad de México.
7. **Rutas de la API:**
   - `POST /searches/{id}/report?format=pdf|html` (§13);
   - `GET /searches/{id}/export?format=csv|geojson`.
   - Una búsqueda que no ha terminado responde `409 search_not_finished`.
8. **Auditoría:** cada reporte o exportación queda en `audit_log` como `report.generated`, con el formato y el usuario (§16).

## Alternativas consideradas

| Alternativa | Por qué no |
|---|---|
| Captura del lienzo del globo enviada por el navegador | Más vistosa (lleva la textura de la NASA), pero un reporte pedido por API saldría sin mapa, y la imagen dependería de dónde quedó la cámara. Benji eligió el mapa del servidor. |
| Librería de mapas estáticos en Python (por ejemplo, matplotlib o cartopy) | Dependencias pesadas para dibujar polígonos que PostGIS ya puede convertir a SVG. |
| Fuentes del sistema (DejaVu) | Funcionan en WSL, pero el resultado cambiaría según el servidor donde se despliegue. |
| Noto Sans variable de Google Fonts | `# VERIFICAR:` WeasyPrint no documenta el soporte de fuentes variables; las versiones fijas no tienen ese riesgo. |
| XML para los datos | Útil si otro sistema lo pidiera así. Para analistas, GeoJSON se abre directo en QGIS o Google Earth. |

## Consecuencias

- **Dependencias nuevas:** `weasyprint` y `jinja2`, más `pypdf` solo en pruebas (lee el texto del PDF para comprobar la Ñ). WeasyPrint necesita Pango ≥ 1.44 y HarfBuzz del sistema: WSL ya tiene Pango 1.57. La guía de despliegue de F8 debe incluirlos.
- **Tabla nueva `reports`:** un resumen ejecutivo por búsqueda, con su modelo, versión del prompt, tokens y costo.
- **Costo:** ~0.001 USD de IA la primera vez que se pide el reporte de una búsqueda; 0 las siguientes. No gasta créditos de SearchApi.
- **Rendimiento:** el PDF se genera durante la petición. Si con ~150 notas tardara más de ~10 s, pasaría al worker de Celery.
- **Estados con muchos municipios** (Oaxaca tiene 570): la geometría se simplifica según el tamaño de la región para que el SVG no pese de más.
