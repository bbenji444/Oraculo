# ADR-0013 — Ingesta periódica e índice local de notas (GDELT por archivos y RSS de medios)

- **Estado:** aceptado
- **Fecha:** 2026-10-16
- **Fase:** F3 (ampliada a "Proveedores e ingesta")
- **Decide:** Benji

## Contexto

Benji quiere usar las tres fuentes de noticias, pero dos de ellas quedaron fuera:

- **GDELT DOC 2.0** respondió 429 de forma persistente (ADR-0012).
- **Google News RSS** tiene términos que solo permiten uso personal y no comercial (ADR-0011).

Hallazgos medidos el 16 de octubre de 2026:

- **El servidor de archivos de GDELT sí responde** (`data.gdeltproject.org`, HTTP 200 en 0.3 s), aunque su API de búsqueda nos bloquee. Cada 15 minutos publica `lastupdate-translation.txt`, que trae el tamaño, el MD5 y la URL de los archivos nuevos.
- **Muestra real del GKG "translingual"** (`20261016191500.translation.gkg.csv.zip`, 7,913,486 bytes, 27 columnas):
  - 2,197 notas en total; **523 en español** (`srclc:spa`); **93 en español con alguna ubicación en México** (`#MX#` en V2Locations).
  - URL y título reales. Ejemplo: "Cayó extorsionador tras cateo en Iztapalapa" (puentelibre.mx).
  - Los títulos llegan con entidades HTML (`&#xF3;`).
  - **Las ubicaciones de GDELT tienen errores:** esa nota de Iztapalapa aparece como "Cuauhtémoc, Guerrero".
- **Términos de GDELT** (https://www.gdeltproject.org/about.html): los datos están disponibles para "unlimited and unrestricted use" en "any academic, commercial, or governmental use of any kind without fee"; "any use or redistribution of the data must include a citation to the GDELT Project and a link to this website".
- **RSS propio de medios:** La Jornada (105 notas), El Universal (100) e Infobae México (100) respondieron. Milenio, Proceso, Animal Político, Excélsior y Aristegui no respondieron en la dirección probada.

## Decisión

1. **Índice local de notas** (`news_index`).
   - Una ingesta periódica junta notas de GDELT (archivos GKG) y de RSS de medios mexicanos.
   - Las búsquedas consultan ese índice con un proveedor nuevo, `indice_local`, **además** de SearchApi en vivo.
   - Se guardan **solo metadatos y link**: título, fragmento, medio, fecha y, de GDELT, sus ubicaciones y temas como pistas. Nunca el artículo completo (CLAUDE.md §8).
2. **Cada 15 minutos**, un reloj de Celery (`celery beat`, arrancado por `make up`) dispara la ingesta.
   - **GDELT:** baja el GKG translingual nuevo, verifica su MD5 y guarda solo las notas en español con alguna ubicación en México.
   - **RSS:** lee los medios activos de `fuentes/medios_rss.csv`. Cada medio queda **inactivo hasta que Benji revise sus términos**.
   - Cada corrida queda en `ingest_runs` y ningún archivo se procesa dos veces.
3. **`indice_local` encuentra candidatos.** Se necesita:
   - al menos una palabra clave en el título o el fragmento (sin acentos, conservando la Ñ, palabra completa);
   - ninguna exclusión;
   - el lugar en el texto, **o** que GDELT haya ubicado la nota en el estado de la región, usando la tabla FIPS→INEGI (`geodata/fips_inegi.csv`);
   - la fecha dentro del rango.

   La Fase 4 confirma la relevancia y geolocaliza con INEGI; las ubicaciones de GDELT nunca se usan como ubicación final.
4. `PlannedQuery` lleva exclusiones y lugar por separado, para que `indice_local` los evalúe sin interpretar el texto armado.
5. **Retención:** las notas del índice se borran a los `NEWS_INDEX_RETENTION_DAYS` (90 días).
6. **Atribución:** cualquier pantalla o reporte que muestre datos de GDELT cita "GDELT Project" con un link a gdeltproject.org, como piden sus términos.
7. La Fase 3 se amplía a **"Proveedores e ingesta"** (especificación v1.8).

## Alternativas consideradas

| Alternativa | Por qué no |
|---|---|
| Insistir con la API DOC de GDELT | Bloqueo persistente (ADR-0012). Sigue el reintento diario de D1 por si se levanta. |
| Usar Google News RSS sin revisar sus términos | Riesgo legal y de bloqueo para la institución (ADR-0011). Queda en manos de Benji y su jefe. |
| Consultar GDELT en BigQuery | Requiere cuenta en la nube y cobro por datos leídos; los archivos son gratuitos y directos. |
| APIs de noticias de pago (mediastack, NewsData.io…) | Precios y cobertura de medios mexicanos sin confirmar; se pueden evaluar después como otro adaptador. |

## Consecuencias

- **Consumo de internet:** unos 760 MB al día (~23 GB al mes) mientras `make up` corra, porque cada archivo de GDELT se baja completo. En disco se guarda poco (~10 MB al día ya filtrado). `GDELT_GKG_ENABLED=false` apaga esta parte sin tocar código.
- **Cobertura:** solo hay notas desde que arranca la ingesta, más el historial que Benji decida bajar (`make ingesta-historial`, con tamaño y confirmación previos).
- **Precisión:** el índice local busca en título y fragmento, no en el texto completo, así que encuentra menos que una búsqueda de texto completo. Se compensa con volumen y con SearchApi.
- La infraestructura de tareas periódicas que pedía F8 queda lista desde ahora.
