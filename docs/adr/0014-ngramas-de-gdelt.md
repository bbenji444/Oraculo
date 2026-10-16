# ADR-0014 — Ngramas de GDELT como fuente del índice local

- **Estado:** aceptado
- **Fecha:** 2026-10-16
- **Fase:** F3
- **Decide:** Benji

## Contexto

Benji pidió encontrar la manera de usar GDELT sin depender al 100% de SearchApi. La API de búsqueda de GDELT (DOC 2.0) sigue sin servir. Así se midió el 16 de octubre de 2026:

- **10 peticiones** espaciadas de 40 a 60 s (GDELT pide 5 s): 6 respuestas 429, 1 vacía (`{}`) y 2 con notas **recortadas** (1 de 5 pedidas y 14 de 50).
- **La primera petición** después de 5 horas sin pedir nada ya recibió 429. El límite no depende de nuestro ritmo.
- **Causa confirmada por GDELT:** la demanda rebasó la capacidad de su sistema viejo, que descarta peticiones en horas pico mientras lo migran a Spanner ([blog de GDELT](https://blog.gdeltproject.org/scaling-gdelt-for-a-new-era-migrating-to-spanner-with-agentic-interactive-gemini/)). No dan fecha para la API de noticias.
- **Nuestra conexión** sale por varias redes privadas del proveedor de internet (192.168.x, 172.26.x, 10.180.x). Probablemente compartimos IP con otros clientes, lo que empeora el límite por IP.
- **El propio mensaje 429 recomienda otra vía:** *"All high-traffic users should switch to our ngrams dataset"* ([guía](https://blog.gdeltproject.org/using-the-new-web-ngrams-dataset-to-find-relevant-coverage/)).

**Qué son los ngramas.** Son archivos de cada minuto en `https://data.gdeltproject.org/gdeltv5/weblegacy/ngrams/`, en pares:

- `AAAAMMDDHHMM00.toc.json.gz`: una nota por línea, con `ID`, `date`, `lang`, `title` y `url`.
- `AAAAMMDDHHMM00.ngrams.txt.gz`: tres columnas separadas por tabulador, `ID`, frase de 4 palabras y número de apariciones, tomadas del **texto completo** de la nota.

Muestra real del 16/10/2026 (`20261016224700`):

- **Tamaño:** 12 MB de ngramas y 412 KB de TOC. Un ciclo de 15 minutos pesa ~11 MB, unos **1 GB al día**.
- **Contenido:** 3,151 notas; **354 en español**, con ~437 frases cada una.
- **México:** 62 de las notas en español mencionan México, un estado o una ciudad grande **en el cuerpo**. Ejemplo: "Casa Tlalpan, ex residencia de Arturo Durazo, se convertirá en universidad" (eldiariodesonora.com.mx).
- **Publicación irregular:** los minutos se publican en tandas y luego hay pausas hasta el siguiente cuarto de hora. No hay un archivo "último" como en el GKG.

## Decisión

1. **Nueva fuente `gdelt_ngrams`** del índice local, ingerida cada 15 minutos por el reloj de Celery.
   - Se procesan los minutos pendientes: un minuto que no existe se ve con un HEAD barato (404) y un minuto ya procesado no se repite (`ingest_runs`).
   - **Entra** una nota si está en español **y** menciona México en su título o su cuerpo. Cuenta "México", el nombre o los términos curados de cualquiera de los 32 estados (del catálogo `regions`), o un dominio `.mx`.
   - **Se guarda** lo de siempre (título, link, medio, fecha). Además se guarda `body_terms`, las frases del cuerpo normalizadas, **solo para buscar**:
     - nunca se muestran ni van a reportes;
     - no son el artículo, porque son frases sueltas sin orden (CLAUDE.md §8).
2. **`indice_local` busca en el título y en `body_terms`**, con las mismas reglas: palabra completa, Ñ y exclusiones. Una frase de más de 4 palabras se aproxima buscando sus partes.
3. **Las frases del cuerpo se conservan 30 días** (`NEWS_BODY_RETENTION_DAYS`); título y link, 90 (`NEWS_INDEX_RETENTION_DAYS`).
4. **Los archivos GKG quedan apagados por defecto** (`GDELT_GKG_ENABLED=false`) cuando los ngramas funcionen, para no sumar 760 MB al día. Se reactivan con la variable. Las notas GKG ya guardadas se conservan.
5. **La API DOC sigue apagada** (ADR-0012). Se revisa cuando GDELT anuncie que terminó la migración.

## Alternativas consideradas

| Alternativa | Por qué no |
|---|---|
| Seguir con la API DOC "si responde" | Funcionó 2 de 10 veces, y recortada. No es confiable para una búsqueda. |
| Seguir solo con el GKG | Solo trae el título: una nota que nombra "Iztapalapa" en el cuerpo no se encuentra. Sus ubicaciones tienen errores sistemáticos (ubicó "Sinaloa" y "Michoacán" como pueblos de Tabasco). |
| GDELT Cloud | Servicio distinto con llaves de pago (desde ~49 USD/mes); entrega eventos agrupados, no búsqueda de notas, y sus datos son irregulares antes de marzo de 2026. |
| GDELT en BigQuery | Exige cuenta de Google Cloud con facturación. Las consultas al GKG cobran por volumen leído. |
| Otras APIs de noticias (NewsData.io, World News API) | Planes gratis chicos y condiciones de uso comercial contradictorias entre fuentes. Se pueden evaluar después con sus términos por escrito. |
| Escribir a GDELT para pedir más cupo | Queda abierto. Lo decide y lo envía Benji. |

## Consecuencias

- **Búsqueda en el texto completo:** el índice encuentra notas que mencionan el lugar o el tema solo en el cuerpo.
- **Internet:** ~1 GB de descarga al día. Con el GKG apagado, el consumo es parecido al de ahora.
- **Disco:** crece por las frases del cuerpo. Se mide con una hora real antes de activar, y la retención de 30 días pone un tope.
- **Formato poco documentado:** GDELT presenta los ngramas como **temporales** y documenta poco su formato (`# VERIFICAR`). Si desaparecen, el GKG se reactiva con una variable.
- **Sin ubicaciones de GDELT:** las notas de ngramas no traen "pistas" de GDELT. Su ubicación la decide F4 con INEGI, y el lugar se sigue buscando en el texto.
