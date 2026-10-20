# ADR-0020: Colonias de OpenStreetMap y reglas nuevas del geolocalizador

- **Estado:** Aceptado
- **Fecha:** 21 de octubre de 2026
- **Decide:** Benji ("quiero que las ubicaciones sean más precisas"), con el diagnóstico de su historial

## Contexto

El historial del 20/10/2026 tenía 75 notas en 5 búsquedas.

**24 notas quedaron sin ubicación:**

| Causa | Notas |
|---|---|
| La IA marcó todos los lugares como "mencionados", ninguno como "lugar del hecho" | 13 |
| El lugar del hecho no estaba en el catálogo | 9 |
| Páginas sin contenido | 2 |

**140 menciones no se resolvieron.** De ellas, 51 empezaban con una palabra genérica: "alcaldía Miguel Hidalgo", "colonia Roma Norte", "calle Molière".

**Hubo ubicaciones equivocadas.**

- **Polanco.** El asesinato del estilista de Micky Hair ocurrió en Polanco, CDMX.
  - La IA dijo "Polanco, Ciudad de México". INEGI no publica colonias, así que no hay ningún "Polanco" dentro de la CDMX.
  - Cuando el filtro por estado se quedaba vacío, el código descartaba la pista del estado.
  - La nota también nombraba Jalisco, y ganó una localidad de Jalisco llamada Polanco.
- **Dos Bocas** (Tabasco) terminó en Veracruz por la misma regla.

El mapa base de México ya descargado (`basemap_mexico.pmtiles`, Protomaps a partir de OpenStreetMap) trae la capa `places`. Ahí están las colonias (`neighbourhood`), las zonas grandes (`macrohood`) y los parajes (`locality`), con su punto. GDAL 3.13 la lee con su driver PMTiles.

## Decisión

1. **Tabla `places`** (migración 0017).
   - Guarda colonias, zonas y parajes de OpenStreetMap dentro de algún municipio de INEGI, con su punto y su municipio.
   - La llena `make geo-places`, sin descargar nada nuevo. El 21/10/2026 cargó 106,810 lugares: 8,998 colonias, 6,212 zonas y 91,600 parajes.
   - Se busca por `name_core`: el nombre normalizado sin palabra genérica ("COLONIA ROMA NORTE" → "ROMA NORTE").
2. **Palabras genéricas.** "Alcaldía", "colonia", "calle", "avenida", "fraccionamiento", "barrio" y otras se quitan del inicio de la mención antes de buscar.
   - Lista única: `GENERIC_PREFIXES` en `app/domain/geocoding.py`. La usan el geolocalizador y la carga de colonias.
   - "Estado de" no se quita, porque "Estado de México" es el estado 15.
3. **El estado que da la IA manda.** Un homónimo de otro estado nunca gana.
4. **Colonias.** Si INEGI no tiene el lugar y se conoce el estado (por la IA o por la región buscada), se busca en `places`.
   - Primero por nombre exacto y luego por familia ("Polanco" → "Polanco 1ª Sección"…).
   - Se acepta solo si todas las coincidencias caen en **un** municipio. "Colonia Centro" existe en muchas alcaldías: ahí decide el municipio que sugiere la IA (prompt v2) o queda ambigua.
   - Resultado: precisión `locality`, punto de la colonia, región = municipio de INEGI, y `article_locations.place_name` con el nombre de la colonia ("Polanco, Alcaldía Miguel Hidalgo").
   - Confianza 0.85 si el nombre es exacto y 0.75 si es por familia (menos que INEGI, porque los nombres los capturan voluntarios).
5. **Último recurso.** Si nada más funciona y la IA dijo el estado, la mención se ubica en ese estado con confianza 0.6, que es justo el umbral. Se pinta con anillo punteado ("aproximada").
6. **Ubicación principal.**
   - Se prefiere el lugar del hecho dentro de la región buscada.
   - Si la IA no marcó ningún lugar del hecho utilizable, se usa el lugar mencionado más específico dentro de la región buscada. Conserva su papel "mencionado", para que la ficha lo diga.

## Alternativas consideradas

- **Catálogo de códigos postales de SEPOMEX.** Tiene colonias oficiales con su municipio, pero no trae coordenadas. Además se descarga desde un formulario, sin una URL estable.
- **Geocodificar con un servicio externo** (Nominatim, Google). Implica dependencia de red, límites de uso y costo. Además rompe la regla de §11 de que los puntos salen del catálogo propio.
- **Pedirle coordenadas a la IA.** Prohibido por §11: la IA inventa.

## Consecuencias

- Las colonias más nombradas en las notas de la CDMX quedan en su punto, no en el centro del estado: Polanco, Roma Norte, Condesa, Nueva Santa María y Santa Cruz Meyehualco.
- OpenStreetMap es de licencia ODbL. El crédito ya aparece en el mapa ("© colaboradores de OpenStreetMap").
- La calidad de las colonias depende de OpenStreetMap, y en ciudades pequeñas hay menos.
- Las calles y los lugares de interés (capa `pois`: parques, hospitales, plazas) no se usan todavía. Son el siguiente paso natural.
- Reubicar el historial (`make reubicar`) aplica las reglas nuevas sin pagarle otra vez a la IA.
