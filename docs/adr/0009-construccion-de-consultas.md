# ADR-0009 — Construcción de consultas a los proveedores de noticias

- **Estado:** aceptado
- **Fecha:** 2026-10-16
- **Fase:** F2
- **Decide:** Benji

## Contexto

Un concepto (palabras clave + exclusiones), una región y un rango de fechas deben convertirse en una consulta por proveedor (especificación §7.2). La Fase 2 arma esas consultas y las muestra en "Probar concepto" sin gastar créditos; la Fase 3 las ejecuta. Hay que decidir dónde vive cada parte de la consulta y qué palabras se usan para nombrar cada lugar.

Datos verificados el 16 de octubre de 2026:

- **Nombres repetidos.** En la base de desarrollo, 233 de los 2,478 municipios comparten nombre con otro de otro estado (90 nombres distintos). "Benito Juárez" existe en 7 estados; "Ocampo" y "Emiliano Zapata", en 6.
- **Nombres oficiales que los medios no usan.** El estado 15 se llama oficialmente "México": como término de búsqueda trae noticias de todo el país. "Veracruz de Ignacio de la Llave", "Coahuila de Zaragoza" y "Michoacán de Ocampo" casi nunca aparecen completos en una nota.
- **GDELT DOC 2.0** ([documentación](https://blog.gdeltproject.org/gdelt-doc-2-0-api-debuts/)): los bloques OR van entre paréntesis y no se pueden anidar. El signo menos excluye "cualquier operador, palabra o frase". `sourcecountry:` acepta el nombre del país sin espacios o su código FIPS de 2 letras. Solo cubre los últimos 3 meses. No documenta un largo máximo de consulta.
- **SearchApi `google_news`** ([documentación](https://www.searchapi.io/docs/google-news)): país con `gl` y lenguaje con `hl`/`lr`. Tiempo con `time_period` (`last_hour`, `last_day`, `last_week`, `last_month`, `last_year`) o con `time_period_min`/`time_period_max` (`MM/DD/YYYY`). Según su [página de precios](https://www.searchapi.io/pricing), solo se cobran las búsquedas que responden 200. No documenta un largo máximo.
- **Natural Earth** trae `ISO_A2_EH` (siempre lleno) y `FIPS_10`, que vale `-99` en algunos países (Noruega) y no siempre coincide con ISO (España: ISO `ES`, FIPS `SP`). SearchApi y Google News RSS usan ISO-2; GDELT usa FIPS.

## Decisión

1. **El texto lo arma el dominio; los parámetros, los adaptadores.**
   - `app.domain.queries.build_queries` produce, por proveedor, el texto exacto de la consulta, con un "dialecto" por proveedor (`app.domain.query_dialects`):
     - formato de frases y OR;
     - exclusiones;
     - filtros que van dentro del texto: `when:7d` en Google News RSS, `sourcelang:` y `sourcecountry:` en GDELT.
   - El país, el idioma y la ventana de fechas viajan aparte, en términos neutros (ISO-2, FIPS, `es`, fechas). Los adaptadores de F3 los traducen a los parámetros de cada API (`gl`, `hl`, `time_period`, `timespan`).
   - "Probar concepto" muestra el texto tal cual se enviará, y los filtros en palabras.
2. **Términos de búsqueda de cada lugar (`regions.search_terms`).**
   - Por defecto se busca por el nombre oficial (`name`).
   - Una lista curada, `geodata/search_terms.csv`, lo reemplaza donde hace falta: CDMX → `"Ciudad de México" OR CDMX`; estado 15 → `"Estado de México" OR Edomex`; Veracruz, Coahuila y Michoacán por su nombre corto; Nezahualcóyotl → `Nezahualcóyotl OR Neza`.
   - `aliases` sigue sirviendo solo para reconocer lugares en el texto de las notas (F4), donde "DF" o "la capital del país" ayudan. En una búsqueda esas frases solo traerían ruido.
3. **Nombres repetidos llevan su estado.**
   - Si un municipio comparte nombre (normalizado) con otro, la consulta exige también los términos de su estado: `"Benito Juárez" ("Quintana Roo")`.
   - Las localidades siempre llevan su estado, porque sus nombres se repiten mucho más.
   - Si el nombre es único, va solo.
4. **País seleccionado:** no se agrega lugar al texto. Se filtra con el país del proveedor.
5. **Códigos de país en `regions`** (`iso_a2`, `fips_code`, solo en países), tomados de Natural Earth.
   - Para GDELT se usa el FIPS. Si no existe, se usa el nombre en inglés sin espacios (`norway`), como permite su documentación.
6. **Idioma:** siempre español. El sistema monitorea prensa en español: `sourcelang:spanish` en GDELT, `es-419` en Google.
7. **Exclusiones en los tres proveedores**, incluido GDELT, porque su documentación confirma el signo menos. Cambia la fila de GDELT en la tabla de §7.2 (especificación v1.4).
8. **Formato:**
   - las frases de varias palabras van entre comillas;
   - un grupo de varios términos va entre paréntesis y unido con `OR`;
   - un término solo va sin paréntesis.

   Las palabras de un concepto no pueden contener comillas, paréntesis, dos puntos, un guion inicial ni `OR`/`AND` sueltos, porque los buscadores los interpretan como operadores.
9. **Largo máximo prudente**, calibrable en F3: 32 palabras para los proveedores basados en Google y 400 caracteres para GDELT. Si una consulta los excede, las palabras clave se reparten en varias consultas.
10. **Créditos estimados:** 1 por consulta en SearchApi y 0 en GDELT y Google News RSS.

## Alternativas consideradas

| Alternativa | Por qué no |
|---|---|
| Que cada adaptador arme su propio texto en F3 | "Probar concepto" no podría mostrar la consulta exacta sin llamar al adaptador, y las reglas de negocio (términos, desambiguación) quedarían repartidas en tres adaptadores. |
| Usar `aliases` también como términos de búsqueda | Mete frases como "la capital del país" o "DF" en todas las consultas de CDMX: más ruido y consultas más largas. |
| Buscar siempre solo por el nombre del lugar | Para "Benito Juárez" mezcla 7 municipios. Para el estado 15 ("México") equivale a no filtrar por lugar. |
| Agregar siempre el estado, también a nombres únicos | Pierde notas que solo dicen "Iztapalapa", sin ganar precisión. |
| Omitir exclusiones en GDELT (como el ejemplo original de §7.2) | Su documentación dice que funcionan; sin ellas GDELT traería cursos y webinars que los otros proveedores sí filtran. |

## Consecuencias

- **Pendientes de F3, marcados con `# VERIFICAR:` en `query_dialects.py`:**
  - varios bloques OR hermanos en GDELT;
  - el rechazo de paréntesis sin OR;
  - el operador `when:` y `after:`/`before:` de Google News RSS, que no es oficial;
  - los límites de largo.

  Se comprueban con una consulta real aprobada. Si alguno falla, solo cambia el dialecto de ese proveedor.
- Agregar el estado puede perder alguna nota que no lo mencione. Se medirá en F4 con resultados reales.
- `search_terms.csv` empieza con pocas entradas y crecerá con el uso (por ejemplo, nombres oficiales largos de Oaxaca). Se aplica con `make geo-terms` sin recargar el catálogo.
