# ADR-0111: Reporte en pantalla, sin descargar el PDF

- **Estado:** aceptado (17/11/2026, plan aprobado por Benji: «Sí, hazlo»).
- **Fase:** F12.

## Contexto

Benji (17/11/2026), por su jefe: «no quiere tener que descargar un archivo cada vez que quiera ver un reporte. Necesita que haya una previsualización del reporte […] como el reporte PDF con todas sus características e incluso hasta mejor, porque pues el HTML sí es dinámico». El PDF debe seguir disponible, pero opcional, con dos botones junto al expediente: «Ver reporte» y «Descargar PDF».

Lo que ya existía:

- El PDF sale de una sola plantilla HTML (`report.html.j2`), convertida con WeasyPrint (ADR-0018, ADR-0033). La API ya devolvía ese HTML (`POST /searches/{id}/report?format=html`), pero solo se usaba para «Imprimir», que estaba oculto.
- Los encabezados de nginx impiden mostrar el monitor dentro de un iframe (`X-Frame-Options: DENY`, `frame-ancestors 'none'`) y no dejan correr CSS ni scripts en línea (`style-src 'self'`). Un HTML puesto en un iframe con `srcdoc` o `blob:` hereda esa política, así que se vería sin estilo.

## Decisión

1. **Ruta nueva `GET /searches/{id}/report/view`.** Devuelve el mismo reporte que el PDF (mismos datos de `BuildReport` y misma plantilla) con lo que solo sirve en pantalla:
   - `report-web.css`: hoja blanca sobre el fondo de Oráculo e índice fijo a la izquierda. En pantallas angostas el índice va arriba, como una tira.
   - `report-web.js`: índice con la sección a la vista marcada, secciones que se pliegan, filtro de noticias por texto y por estado, la cifra exacta al pasar el mouse por barras, dona, línea del tiempo y mapa, cifras que cuentan y links en otra pestaña.
   - Las cifras de las ayudas salen de atributos `title` y `<title>` de SVG en la plantilla, que WeasyPrint ignora. El PDF no cambia.
   - Las fuentes WOFF2 (~150 KB) van incrustadas como `data:`, para que la página no pida archivos. Las TTF de Noto Sans (1.2 MB) se quitan y el navegador usa su sans-serif.
2. **Es `GET` porque la abre un iframe.** Igual que el `POST`, la primera vez puede pedirle el resumen ejecutivo a la IA (~0.0003 USD). Otro sitio no puede provocarlo: la cookie de sesión es `SameSite=Strict`.
3. **Política propia para esa respuesta.** La pone la API:
   - `default-src 'none'`, `script-src 'nonce-…'` con un nonce nuevo en cada respuesta, `style-src 'unsafe-inline'`, `img-src data:`, `font-src data:`, `frame-ancestors 'self'`;
   - `X-Frame-Options: SAMEORIGIN` y `Cache-Control: no-store`.

   nginx tiene un `location` solo para esa ruta (`encabezados-reporte.conf`) que no repite la política general. Si la repitiera, el navegador aplicaría las dos y bloquearía el estilo.
4. **En el monitor** (`Mando/ReportViewer.tsx`):
   - «Ver reporte» y «Descargar PDF» van en su propio renglón del expediente, debajo del título. Junto al título lo dejaban en tres letras.
   - «Ver reporte» abre una ventana casi de pantalla completa con el iframe. Se cierra con «×», con Esc (también con el foco dentro del reporte) o con un clic afuera. La ventana repite «Descargar PDF».
   - El diseño clásico (`?clasico`) conserva su botón de PDF.
5. **`sandbox="allow-scripts allow-same-origin allow-popups allow-popups-to-escape-sandbox"`.** Sin formularios ni navegación de la página de arriba. Se conserva el origen porque, sin él, el navegador del panel de Claude bloqueó la página (`ERR_BLOCKED_BY_CLIENT`). Lo que protege de un título malicioso es la política: Jinja escapa todo, y aunque algo se colara, ningún script sin el nonce corre ni puede pedir nada a ningún servidor.

## Alternativas consideradas

| Alternativa | Por qué no |
|---|---|
| Reescribir el reporte en React | Duplicaría unas 470 líneas de plantilla y 2,000 de CSS. El PDF y la vista se irían separando con cada cambio. |
| Abrir el HTML en otra pestaña | Es casi una descarga: saca al analista del monitor. Además, la política de nginx le quitaría el estilo. |
| `srcdoc` o `blob:` en el iframe | Heredan la política del monitor (`style-src 'self'`): el reporte se vería sin estilo y sin script. |
| Aflojar la política de todo el sitio | Expone todas las pantallas para resolver una sola. |
| `sandbox` sin `allow-same-origin` | Más aislado, pero el navegador del panel lo bloqueó, y el nonce ya impide scripts ajenos. |

## Consecuencias

- El jefe lee el reporte dentro del monitor. El PDF se baja solo si lo quiere.
- La vista cuesta lo mismo que el PDF: el resumen se paga una vez por búsqueda y se reutiliza.
- **Al publicar en la VM**, `make up` regenera el sitio de nginx desde la plantilla. Sin ese `location`, la ventana saldría en blanco, porque el monitor no deja incrustarse a sí mismo.
- Cambiar `report-web.css` o `report-web.js` requiere reiniciar la API: se leen al arrancar, igual que `report.css`.
