# ADR-0114: Relevancia estricta en los conceptos «como en Google» y la búsqueda rápida

- **Estado:** aceptado (19/11/2026, Benji: «Sí, apruébalos»; propuesto el 18/11/2026).
- **Fase:** F12 (búsqueda «casi tan natural como Google», punto 4).
- **Ajusta:** ADR-0109 (D4, juicio de los conceptos abiertos con `enrich_v5`) y ADR-0113 (D5, los términos obligatorios todavía no se usaban para juzgar).
- **Relacionados:** ADR-0115 (Google web, `searchapi_web`) y ADR-0117 (la pantalla de las no relevantes).

## Contexto

Benji, 18/11/2026: «las relevantes deben hablar de verdad de lo pedido y las no relevantes no deben ser basura total». Lo que se vio en la VM ese día:

- **«hacker eternal»** (búsquedas 35 y 36). Google News RSS trajo notas reales del caso, como «Hackean Buró Laboral y exponen datos de miles de trabajadores», cuyo título no dice «Eternal». Su link es de Google y no se puede descargar, así que la IA solo vio el título. Con «Si dudas, NO es relevante», las marcó no relevantes. Al mismo tiempo, notas de hackeos de otros grupos pasaban como relevantes porque eran «del mismo tema».
- **«roban vehículos en Jalisco»** (789b2553). Entre las notas había «Concentración feminista en Guadalajara» y «Cancelan vuelos desde Guadalajara». Llegaron porque la consulta nombra el lugar. La IA las juzgó, se pagaron y quedaron en la lista de no relevantes como si fueran del tema.
- **El juicio no sabía dónde se buscaba.** `enrich_v5` empieza con «…noticias geolocalizadas sobre México». En una búsqueda en «Mundo» (ADR-0112) descartaba lo que pasaba fuera de México.
- **`is_relevant` es un sí o un no.** No hay forma de distinguir entre «es exactamente esto», «muy probable pero falta leer la nota», «del tema pero de otra entidad» y «nada que ver».

ADR-0113 ya dejó en cada concepto de la búsqueda rápida sus `required_terms`: los nombres propios que escribió el analista, comprobados contra su texto («eternal»). Todavía no se usaban.

## Decisión

Solo cambian los **conceptos abiertos** (`query_mode=open`: los «como en Google» y la búsqueda rápida). Los conceptos exactos y el monitor FGR quedan exactamente igual.

### 1. Filtro de palabras antes de la IA (`domain/core_terms.py`)

Cada consulta de un concepto abierto lleva un `CoreTerms` (`PlannedQuery.core`, puesto por `plan_queries` con `core_of`). Tiene dos partes:

- **Entidades (estricto):** los `required_terms` del concepto. La nota tiene que nombrar cada una, como palabras completas, en el título o el fragmento. La comparación usa la misma normalización del índice local: mayúsculas, sin acentos, conservando la Ñ. «Eternals» no es «Eternal»; «Cartel de Sinaloa» sí es «Cártel de Sinaloa».
  - **Apellido** (revisión del 18/11/2026, prueba real). Un nombre de persona de dos o tres palabras, sin palabras de enlace, también cuenta con su última palabra si tiene 5 letras o más (`term_aliases`): «Harfuch confirma la captura de El Topo» nombra a «Omar García Harfuch». Exigir el nombre completo dejó 40 notas «por confirmar», con la pista falsa al juez de que el título no lo nombraba, y tiró 44 del índice local antes de la IA. Los nombres con palabras de enlace o cortas («Fiscalía General de la República», «Los Deltas», «El Mencho») son instituciones o alias, igual que los de apellido corto («Octavio Paz»): «República» o «Paz» sueltos dirían otra cosa. Con cuatro palabras o más la última ya no es seguro que sea un apellido («Generación» de «Cártel Jalisco Nueva Generación»).
  - **Sigla** (misma revisión, prueba real «cateo de la Fiscalía General de la República», último día). Con tres palabras de contenido o más, el término también cuenta con sus iniciales: «FGR», «CJNG», «AMLO», «SSPC». Los títulos nombran así a las instituciones («FGR asegura 2 predios por tala ilegal en Balancán»), y exigir el nombre completo tiró 90 notas antes de la IA. Las palabras de enlace (artículos, preposiciones, conjunciones: `CONNECTORS`) no dan letra; «Nueva» sí. Con 2 letras («CS» de «Cártel de Sinaloa») o si la sigla se lee como palabra vacía («MAS» de «Mesa Ampliada de Seguridad») no cuenta: diría otra cosa. La sigla es palabra completa, así que «FGE» no pasa por «FGR».
- **Tema (laxo):** las raíces de las palabras de lo que escribió el analista y de sus frases. Se omiten las palabras vacías, el lugar de la búsqueda, los números y los mismos términos obligatorios. Basta con que la nota tenga **una** raíz.
  - Las raíces salen de un recorte propio del español (`stem`): quita un plural y después la terminación más larga (`ROBARON`→`ROB`, `HACKEADAS`→`HACK`, `VEHÍCULOS`→`VEHICUL`) y deja al menos 3 letras.
  - Dos palabras empatan solo si su raíz es **igual**, no si una empieza como la otra. Así `ROBERTO` (→`ROBERT`), `ROBOT`, `AUTORIDAD`, `AUTOR` y `AUTOMÓVIL` no empatan con «robo» ni con «autos».
  - Las terminaciones `-OR`, `-ORES` y `-AD` no se recortan a propósito: si se recortaran, `AUTOR` y `AUTORIDAD` quedarían en `AUT`.
  - El recorte **no** junta todas las formas de una palabra: `DESAPARICIONES`→`DESAPARI` y `DESAPARECIDOS`→`DESAPAREC`; `HUACHICOLEROS`→`HUACHICOLER` y `HUACHICOL`→`HUACHICOL`; «ataque» y «atacan», «violencia» y «violento» tampoco empatan, y un sinónimo («hidrocarburo» por «huachicol») nunca. Cuando falla, **tira** una nota del tema antes de la IA. Por eso el tema solo se exige donde el buscador no exigió ya las palabras (abajo).
  - Si el analista solo escribió un nombre («LockBit en Jalisco»), no se exige tema. Las frases de la IA («LockBit ataque») meterían un tema que nadie pidió y tirarían «Detienen al líder de LockBit».
- **Qué se exige depende de cómo llegó cada nota** (`QueryOrigin`, uno por nota: `origin_of(consulta, nota)`). Revisión del 18/11/2026 (hallazgos 2 de la revisión 0 y 3 de la revisión 1):

  | Procedencia | Ejemplos | Tema | Entidad |
  |---|---|---|---|
  | Texto completo (`full_text`) | Google News RSS, SearchApi (Google News) y los resultados **orgánicos** de Google web (`raw["section"] = "organic_results"`) | **no** se exige: Google ya exigió las palabras en el cuerpo; decide el juez y la banda «ajena» lo esconde | sí, con la excepción por procedencia |
  | Carrusel de Google web (`carousel`) | `inline_videos`, `inline_shorts`, `inline_tweets`, `top_stories`, `perspectives`, `discussions_and_forums` | solo si el concepto no tiene entidad | sí, en el título, el fragmento **o el canal o autor** (`source_name`); si la nombra, pasa aunque no traiga la raíz del tema |
  | Lo demás | índice local, GDELT, BrowserWork | sí | sí, en el título o el fragmento |

  Títulos reales que antes se tiraban por tema y ahora llegan al juez: «Aseguran 2 mil 500 litros de hidrocarburo y camioneta en Tlahuelilpan» (huachicol en Hidalgo, RSS) y «DIPUTADAS Y DIPUTADOS CUESTIONAN AL FISCAL DE JALISCO SOBRE DETENCIONES, DESAPARICIONES Y EL CASO DEL RANCHO IZAGUIRRE» (desaparecidos en Jalisco). En el índice local siguen fuera. De los 4 videos del fixture real de Google web (`searchapi_web_hacker_eternal_7d.json`) pasa solo el de La Saga («ETERNAL expone 746 MIL cuentas de PILLOFON…»); antes se tiraba por no decir «hacker» y pasaba «por confirmar» el genérico de UnoTV.
- **Excepción por procedencia.** Una nota que no nombra la entidad **pasa sin confirmar** si llegó por una consulta que sí la lleva, en un buscador que busca en el texto completo de la nota (la primera fila de la tabla). Si Google la trajo por «hacker eternal», Eternal está en el cuerpo de la nota.
  - El índice local busca solo en título y resumen (ADR-0013), así que no cuenta. GDELT y BrowserWork no se han medido, así que tampoco cuentan. Los carruseles de Google web no buscan en el texto completo, así que tampoco.
- **Lo que no pasa** ni se guarda ni se paga a la IA. Se cuenta en `progress.off_core` (notas distintas) con hasta 5 títulos en `off_core_samples`.
  - Una nota que tira la consulta de un concepto abierto, pero que trae también otra consulta de la misma búsqueda (por ejemplo, de un concepto exacto), se queda y no cuenta como descartada.

El filtro corre en `RunSearch._dedupe`, **justo antes de `_on_topic`** (la palabra de la subdivisión). Necesita saber qué consulta trajo cada nota, y `_on_topic` ya devuelve todas las notas juntas. El resultado es el mismo en cualquier orden, porque los dos filtros miran cada nota con su propia consulta. Lo único que cambia es qué contador suma una nota que falla los dos: suma en `off_core`.

### 2. El juez sabe cómo llegó cada nota

Después de deduplicar, `_trace_origins` anota en cada nota las consultas que la trajeron (`QueryOrigin`: el buscador, su nombre en pantalla, las frases, si busca en el texto completo y, en Google web, la sección). Las copias de una nota se reconocen igual que en `dedupe`: por link canónico o por título normalizado. `EnrichmentRequest` lleva ahora:

- `region`: el nombre de la región buscada (`display_name`);
- `origins`: hasta 5 procedencias; un carrusel sale como «Google web, videos»;
- `unconfirmed_terms`: las entidades de los conceptos abiertos que el título y el fragmento no nombran;
- `entity_context` (revisión del 18/11/2026, hallazgo 4): **lo que se sabe de esas entidades** por otras notas de la misma búsqueda que sí las nombran (`CoreMatcher.entity_context`, por `judge_hints`). Son hasta `MAX_CONTEXT_FRAGMENTS = 6` fragmentos de hasta `MAX_CONTEXT_CHARS = 220` caracteres (título y fragmento), sin repetir título, en el orden del buscador. Unos 350 tokens más solo en las notas sin confirmar.

`ReprocessSearch` (`make reubicar --con-ia`) manda lo mismo, rearmado con lo guardado (revisión del 18/11/2026, hallazgo 5):

- la procedencia sale de `search_results.provider` (qué proveedores trajeron la nota) y de `provider_queries.query_text` (qué consultas respondieron a cada uno). Cuentan las consultas que nombran la entidad (`rebuilt_origins`);
- Google web no guarda la sección de cada nota, así que al reprocesar **no cuenta como texto completo**;
- las entidades sin confirmar y su contexto salen de los títulos y fragmentos guardados de la búsqueda.

Antes de pedir el «si», el comando avisa lo que no se puede rearmar (`ReprocessSearch.warnings`): que no se sabe cuál consulta trajo cada nota, la sección de Google web, que no hay consultas guardadas, o que el concepto no guardó su entidad (búsquedas de antes de la migración 0049, como la 35 y la 36). Con solo conceptos exactos no avisa nada ni lee la procedencia.

### 3. Prompt `enrich_v6`

`enrich_v6.md` es la plantilla de `enrich_v5.md` con tres huecos: la primera línea (`{intro}`), el bloque de reglas de los conceptos abiertos (`{open_rules}`) y la procedencia (`{origins}`).

- **Con solo conceptos exactos** (FGR, temas) el texto es el de `enrich_v5` **letra por letra**:
  - la primera línea es la de v5, «…sobre México»;
  - el bloque de abiertos de v5, que sin conceptos abiertos no hace nada, está copiado tal cual en `enrich_v6_exact.md`;
  - no lleva procedencia, aunque la búsqueda la traiga.

  Una prueba compara el prompt completo con `enrich_v5.md` llenado a mano.
- **Con algún concepto abierto** (`enrich_v6_open.md`):
  - La primera línea dice «La búsqueda es en: {región}» y ya no dice «sobre México».
  - Es relevante solo si el asunto central es **exactamente lo que pide** el analista. «Mismo tema general no basta.» Cifras, investigaciones o denuncias de lo pedido sí cuentan, porque no se exige un hecho concreto.
  - «Debe hablar de: …»: una nota del mismo tema sin esa entidad no es relevante; es cercana. «La única excepción es la de procedencia, más abajo»: así ya no chocan las dos reglas.
  - El lugar lo revisa el sistema con la región: la IA no descarta por país o lugar, salvo que el analista pida expresamente un lugar distinto de la región.
  - Las alertas genéricas, las guías («cómo protegerte»), los recuentos de varios casos, las estafas de temporada, la publicidad y lo que solo lo nombra de pasada son cercanas.
  - Procedencia (revisión del 18/11/2026, hallazgo 4). Si solo hay título, el título no nombra la entidad, pero la nota llegó por una consulta con ella en un buscador de texto completo:
    - es relevante «por confirmar», con 0.65 a 0.75, **solo si el título coincide con un hecho concreto de lo que se sabe de la entidad** (el bloque `entity_context`: la misma víctima, empresa, institución, dato filtrado o cifra). «Revelan listas negras laborales; vende hacker datos» coincide con el hackeo de Eternal al Buró Laboral;
    - si solo es del mismo tema, o no se sabe nada de la entidad, es **cercana**, con 0.35 a 0.5, y la razón dice «El título no nombra a X y no coincide con lo que se sabe de X». «Ariana Grande demanda a hackers», ruido que Google trajo por «hacker eternal», queda aquí;
    - si no tiene que ver con el tema, es ajena.

    Antes bastaba con que el título fuera «coherente con el tema»: casi todo el RSS llega solo con título, así que en una búsqueda de entidad casi toda nota del tema salía «por confirmar». Es la única excepción a «Si dudas, NO es relevante».
  - Las bandas van escritas en el prompt (ver la sección 4). `is_relevant` es true solo con 0.6 o más.
- **Búsqueda mixta** (un concepto exacto, como la FGR, y uno abierto en la misma búsqueda manual; revisión del 18/11/2026, hallazgo 6): la primera línea sigue siendo la de v5, «…sobre México», más «Los conceptos que traen «Lo que busca el analista» se buscan en: {región}». Al final de las reglas de los abiertos se aclara que la regla de lugar y las bandas son solo para ellos. El juicio del exacto sigue con las reglas generales, pero su prompt ya no es el de v5 letra por letra: lleva las reglas de los abiertos, que no le aplican.

### 4. Bandas de relevancia (`domain/authority.py`, sin migración)

- `MIN_RELEVANCE_SCORE` sigue en 0.6. Son nuevos `CONFIRMED_RELEVANCE_SCORE = 0.8` y `MIN_RELATED_SCORE = 0.3`.
- `relevance_band(is_relevant, score, query_mode)` da una de cuatro bandas en los conceptos **abiertos**:

  | Banda | Cuándo |
  |---|---|
  | `relevant` | relevante con 0.8 o más |
  | `unconfirmed` | relevante con 0.6 a 0.79 (relevante «por confirmar») |
  | `related` | no relevante con 0.3 o más («cercana») |
  | `unrelated` | no relevante con menos de 0.3 («ajena») |

- En los conceptos **exactos** (FGR, temas) solo hay dos (revisión del 18/11/2026, hallazgo 1): relevante es `relevant` y no relevante es `related`, sin importar el puntaje. Su prompt (el de v5) no define bandas: casi todo «no» lleva de 0 a 0.2, y como «ajena» nunca se muestra (ADR-0117), el interruptor «Incluir las no relevantes» del monitor FGR quedaba vacío (2020 de 2021 no relevantes de la FGR en la base de desarrollo tenían menos de 0.3; «Confirma Fiscalía orden de aprehensión contra Vadhir», con 0, nunca se veía). Los 121 relevantes FGR de 0.6 a 0.79 tampoco llevan «Por confirmar».
- Se calcula **al leer**, con la relevancia final (ya con la regla FGR y el umbral) y el `query_mode` copiado en `search_concepts` (o el del concepto, en la lista de notas), y sale en `concepts[].relevance_band` de las notas de la API. No se guarda: cambiar los cortes no pide migración ni reprocesar.

### 5. `make revisar-relevancia` (solo lectura)

`app/cli/revisar_relevancia.py` con el caso de uso `ReviewRelevance` y sus puertos de solo lectura (`ports/relevance_review.py`). Muestra de una búsqueda (por defecto, la última):

- lo que pidió el analista, sus frases, los términos obligatorios y la región;
- los contadores del avance, con los títulos que tiró el filtro;
- cuántas notas hay en cada banda y cuántas caen fuera de la región;
- una fila por nota: banda | puntaje | región | texto | proveedores | título (70) | razón (140), de la banda más alta a la más baja.

La conexión se abre con `default_transaction_read_only=on`: aunque hubiera un error, PostgreSQL no deja escribir. No gasta créditos ni tokens. Sirve para medir con búsquedas reales y compararlas con Google sin volver a gastar.

## Alternativas consideradas

- **Dejarlo todo al prompt, sin filtro en el código:**
  - Pros: menos código; la IA entiende sinónimos y alias.
  - Contras: se paga por juzgar «Concentración feminista en Guadalajara». Además, un prompt no garantiza nada: con «Si dudas, NO es relevante» la IA ya se equivocó en las dos direcciones. El filtro solo tira lo que no tiene ni una palabra del tema o no nombra la entidad, y lo dudoso lo deja pasar a la IA.
- **Exigir la entidad sin excepción:**
  - Pros: es más simple y nunca deja pasar algo sin la entidad.
  - Contras: tira justo las notas correctas de Google News RSS cuyo título no la nombra («Hackean Buró Laboral…»), que son la mitad de lo que Benji encontró en Google.
- **Comparar por prefijo** (la nota tiene una palabra que empieza como la del pedido):
  - Pros: no hace falta recortar terminaciones.
  - Contras: `ROB` empata con Roberto y robot; `AUT` con autoridad, autor y automóvil. Es el error que se quería evitar.
- **Usar un recortador de una librería** (Snowball, spaCy):
  - Pros: está probado.
  - Contras: es una dependencia nueva y `domain/` no importa librerías externas. No se midió cómo recortan `AUTORIDAD`, `ROBERTO` o `ROBOT`, que son los casos que importan aquí. Para este filtro laxo, unas 30 terminaciones bastan y se prueban caso por caso.
- **Filtrar después de `_on_topic`:**
  - Pros: los contadores de siempre no cambian.
  - Contras: `_on_topic` devuelve las notas sin su consulta y el filtro necesita saber cuál las trajo (sus entidades y su procedencia).
- **Guardar la banda en la base:**
  - Pros: se podría filtrar por banda en SQL.
  - Contras: pide migración y reprocesar si cambian los cortes. Calcularla al leer es instantáneo.
- **Un prompt nuevo solo para los abiertos, sin tocar la versión de los exactos:**
  - Pros: el monitor FGR no se volvería a juzgar.
  - Contras: la caché va por una sola versión de prompt (`PROMPT_VERSION`); dos versiones vivas a la vez piden cambiar `reusable_for`, el guardado y los reportes. El texto de los exactos no cambia, así que el criterio de la FGR es el mismo y solo se paga una vez de más.

## Consecuencias

- **Costo de invalidar la caché.** Cambiar a `enrich_v6` hace que cada nota guardada se vuelva a juzgar **una vez** la próxima vez que aparezca en una búsqueda, aunque sea de un concepto exacto o de una corrida FGR. Con OpenAI (unos 0.00024 USD por nota, `.env.example`) son unos 0.03 USD por búsqueda de 120 notas, y hasta 0.06 USD en una corrida FGR con el tope de 250. Después se reutiliza como siempre. Las reglas de los abiertos tienen unas 310 palabras más que las de v5 (542 contra 231, unos 0.00005 USD más por nota). No gasta créditos de SearchApi.
- **El criterio de la FGR y los temas no cambia:** su prompt es idéntico al de v5 (salvo en una búsqueda mixta, arriba), no pasan por el filtro de palabras y sus bandas son solo `relevant` y `related`.
- **Más notas llegan al juez y se pagan.** Lo que trajo Google con texto completo ya no se tira por tema: en la simulación de la revisión con títulos reales de «huachicol en Hidalgo», 6 de 8 se tiraban por tema; si los trajo Google, ahora llegan a la IA (unos 0.00024 USD por nota con OpenAI). El tope `LLM_MAX_ARTICLES_PER_SEARCH` sigue mandando.
- **El contexto de la entidad encarece un poco las notas sin confirmar** (unos 350 tokens de entrada cada una) y depende de que la búsqueda traiga alguna nota que nombre la entidad. Si ninguna la nombra, el prompt lo dice y esas notas quedan, a lo más, cercanas.
- **Lo que se tira ya no se ve.** Una nota sin la entidad, que llegó por el índice local o un carrusel, ya no sale ni en la lista de no relevantes. Para revisar qué se tiró están `off_core_samples` y `make revisar-relevancia`.
- **El recorte de raíces solo decide fuera de los buscadores de texto completo** (índice local, GDELT, BrowserWork, carruseles). Ahí puede dejar pasar una palabra de la misma raíz pero de otro tema («datos» en una nota de futbol), que juzga la IA, y también puede tirar una nota del tema escrita con otra forma o un sinónimo. Si aparece un caso, se agrega a `_ENDINGS` o a `STOPWORDS` con su prueba.
- **`reubicar --con-ia` no repite exactamente el juicio en vivo** en los conceptos abiertos: rearma la procedencia por proveedor, no por consulta, y Google web cuenta como sin texto completo. El comando lo avisa antes de gastar.
- **Casi duplicados.** Si dos copias de la nota tienen títulos casi iguales (similitud ≥ 0.9) pero no idénticos, la copia que se queda no hereda la procedencia de la otra. El juez ve solo la de las copias que coinciden por link o título exacto.
- **La IA tiene que respetar las bandas.** El prompt las pide, pero no se ha medido con el modelo real. Si la IA da 0.9 a una nota «por confirmar», sale `relevant`.
- **`region` no forma parte de la llave de caché.** Una nota ya juzgada con `enrich_v6` en una búsqueda de «Jalisco» se reutiliza en una de «Mundo» sin volver a juzgarse. Pasa lo mismo que con los conceptos: la caché va por versión y por conceptos juzgados.
- **Se cuentan distinto dos casos.** Una nota de un concepto abierto que no tiene la palabra de la subdivisión ni lo pedido ahora suma en `off_core`, no en `off_topic`.
- **Pruebas que cambiaron porque cambió el requisito** (no se debilitaron):
  - `test_run_search.py::test_la_ia_tiene_a_mano_los_terminos_obligatorios`: la búsqueda rápida «hacker eternal» ya no deja pasar a la IA las notas de extorsión de las fuentes de siempre, así que la prueba usa una nota que sí habla de Eternal.
  - `test_gemini.py`: la versión es `enrich_v6`, y la regla «No exijas un hecho concreto» ahora empieza con mayúscula.
  - Revisión del 18/11/2026: en `test_run_search_core.py`, las notas sin el tema que se esperaba ver descartadas vienen ahora del índice local (las de SearchApi llegan al juez, con su propia prueba); en `test_core_terms.py`, «Eternal Sunshine…» y «Concentración feminista…» se descartan por tema solo si no las trajo Google; en `test_llm_enrich_v6.py`, la procedencia ya no se marca «por confirmar» por ser «coherente con el tema» y la búsqueda mixta conserva «sobre México»; en `test_authority.py`, `relevance_band` recibe el modo del concepto.
- **No se probó con la IA ni con los proveedores reales.** Hay que repetir «hacker eternal» y «roban vehículos en Jalisco» y revisarlas con `make revisar-relevancia`. Al publicar hay que reiniciar la API **y el worker**.
