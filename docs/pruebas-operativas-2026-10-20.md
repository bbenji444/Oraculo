# Pruebas operativas de usuario — 20 de octubre de 2026

Benji pidió, antes de pasar de la sub-fase 9.1 a la siguiente, cuatro pruebas como las haría un analista: usar la aplicación de punta a punta, encontrar áreas de oportunidad y corregirlas.

## Cómo se hicieron

- **Dónde:** navegador integrado de la app, contra los servicios locales (`http://localhost:8080`), con los datos reales ya guardados (7 búsquedas del 17 al 20 de octubre).
- **Sin gastar:**
  - no se lanzó ninguna búsqueda nueva, para no gastar créditos de SearchApi ni de la IA;
  - el reporte PDF se generó con una búsqueda que ya tenía su resumen guardado, así que no se pagó de nuevo.
- **Cómo se midió:**
  - las descargas se revisaron con `curl` contra la API local;
  - el PDF se leyó con `pypdf`;
  - el contraste del texto se midió con los píxeles de las capturas, con la fórmula de WCAG.

## Las cuatro pruebas

| # | Tarea del analista | Pasos | Resultado |
|---|---|---|---|
| 1 | Retomar una investigación | Historial → "Abrir en el globo" (Homicidio · Miguel Hidalgo, 43 notas) → elegir una nota en la lista → ficha → "Ver nota original" → clic en el grupo de Polanco | Funciona: vuela a la alcaldía, la ficha trae fecha del hecho, resumen y lugar preciso, y el grupo abre "9 notas en este lugar". Hallazgos 1, 2 y 3. |
| 2 | Preparar una búsqueda nueva | Editar → buscador "monterey" (con error de dedo) → Monterrey → conceptos → fechas al revés | El globo y los filtros se sincronizan. Con fechas al revés aparece "La fecha final es anterior a la inicial." y Buscar se apaga. Hallazgos 4 y 5. |
| 3 | Crear y probar un concepto | Conceptos → Nuevo concepto "Narcomenudeo" con tres palabras clave → Probar concepto en "san pedro" → Ver consultas | Los chips y la vista previa funcionan sin guardar ni gastar. Hallazgos 5 (otra vez) y 6. |
| 4 | Entregar resultados | PDF, CSV y GeoJSON de una búsqueda guardada | PDF de 5 páginas en 3.6 s. El CSV trae BOM y columnas en español; el GeoJSON trae puntos con propiedades. Hallazgos 7 y 8. |

## Hallazgos y qué se hizo

Rama `fix/pruebas-operativas` (sale de `feat/precision-y-paginacion`), un commit por corrección.

| # | Hallazgo | Evidencia | Corrección | Commit |
|---|---|---|---|---|
| 1 | La búsqueda dice "43 notas" y la lista "Noticias (24)", sin explicar que 19 se ocultaron por no relevantes | Al activar "No relevantes" sube a 43 | El encabezado dice "Noticias (24 de 43)" y su ayuda explica las ocultas | `0ed5889` |
| 2 | En modo día, la línea "medio · fecha · lugar" de cada nota casi no se lee | Contraste 1.6 : 1 medido en pantalla (se pide 4.5 : 1) | De día el vidrio de los paneles se oscurece y esa línea va un tono más clara: **6.1 : 1**. De noche no cambia | `2735554` |
| 3 | El Historial muestra "2026-09-20 a 2026-10-20"; Explorar, "13 – 20 oct 2026" | Captura | El Historial usa el mismo formato | `84384bd` |
| 4 | Con el error de dedo "monterey", sale primero el país **Montenegro** y después el municipio Monterrey | Parecido 0.4 contra 0.6; el SQL ordenaba por nivel antes que por parecido | En coincidencias aproximadas manda el parecido; lo exacto y lo que empieza igual siguen por nivel. Primera prueba de integración del buscador | `4b84d76` |
| 5 | Los homónimos solo se distinguen por la clave INEGI ("Municipio San Pedro · 05033" frente a "San Pedro Garza García · 19019") | Captura | Cada resultado dice su estado: "Coahuila de Zaragoza · Municipio · 05033" | `1a5f519` |
| 6 | "Probar concepto" dice "4 consultas" (incluye Google News RSS y GDELT) y Explorar estima 2 | Una búsqueda solo usa SearchApi y el índice local (`SEARCH_PROVIDERS`) | La vista previa usa los mismos proveedores que la búsqueda real | `6171bb3` |
| 7 | **El PDF contradecía la pantalla:** "0 en Miguel Hidalgo · 0 %, 11 fuera de la región", y la pestaña "Dentro" mostraba 8 | Búsqueda en la localidad cabecera homónima 090160001; el reporte no usaba la regla `seat_area` (ADR-0020) | El reporte cuenta y dibuja el mapa con la misma regla que la pantalla: **8 dentro (73 %), 3 fuera** | `c8a1045` |
| 8 | Las descargas traen 11 notas y la búsqueda tiene 19, sin aviso | Por diseño solo llevan las relevantes (ADR-0018) | La ayuda de PDF, CSV, GeoJSON y del encabezado lo dice | `0ed5889` |

## Lo que queda para decidir (no se cambió)

1. **El resumen de IA guardado puede quedar viejo.**
   - El PDF de "Homicidio · Miguel Hidalgo" dice "12 notas relevantes" en el resumen y 11 en la portada.
   - El resumen se escribió antes de que una nota cambiara de relevancia, y se guarda para no volver a pagarlo.
   - **Propuesta:** guardar junto al resumen cuántas notas resumió y regenerarlo si cambia (~0.0003 USD cada vez). Pide una migración, así que espera tu visto bueno.
2. **"San Pedro Garza García" se busca solo con su nombre completo.**
   - Muchas notas dicen "San Pedro, Nuevo León" y esas no entrarían.
   - Agregar "San Pedro" como término de búsqueda de ese municipio es una decisión de curaduría (ADR-0009): puede traer notas de otros San Pedro.
3. **Notas repetidas del mismo hecho.** En Polanco, 9 notas de distintos medios cuentan el mismo caso. Agruparlas por hecho es justo lo que hará el caso de investigación de la Fase 9.
4. **Costo del buscador.** El nuevo orden hace un poco más lenta la consulta más amplia, una de 3 letras ("san", que coincide con miles de localidades): de 0.40 a 0.46 s en la base. No se notó en pantalla.

## Cómo repetirlas

```bash
wsl make up
```

Después, abrir `http://localhost:8080` y seguir los pasos de la tabla. Para las descargas:

```bash
curl -s -o reporte.pdf -X POST "http://localhost:8080/api/v1/searches/<id>/report?format=pdf"
```
