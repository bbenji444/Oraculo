# ADR-0109: Conceptos «como en Google»: frases tipo titular, una consulta por frase

- **Estado:** aceptado (17/11/2026, plan de búsquedas abiertas aprobado por Benji con las decisiones D1 a D6).
- **Fase:** F12.

## Contexto

Benji (17/11/2026): «al yo limitarme a poner palabras claves en un concepto, no me da toda la cantidad de resultados de calidad como si yo buscara la noticia de manera normal en Google. Y necesito que sea lo más cercano a eso sin traer noticias basura».

Medición sin gastar créditos:

- **Búsquedas guardadas en la VM** (solo lectura):
  - El 17/11, el concepto «bases de datos hackeadas» llevaba la frase `"bases de datos hacked"` y trajo **0 notas**.
  - Con `bases de datos | hackeadas | hacking bases de datos` trajo 38 notas, y **4 eran relevantes**.
  - Las búsquedas por estado traen poco: en Guanajuato salieron 16 notas y 1 relevante.
- **Google News RSS, 13 consultas gratis** de los últimos 7 días con `gl=MX`:

  | Consulta | Notas |
  |---|---|
  | `"bases de datos hackeadas"` | 0 |
  | `bases de datos hackeadas` | 10 |
  | `filtran datos` | 29 |
  | `("robo de vehículo" OR "robo de auto" OR "robo de camioneta") Jalisco` | 5 |
  | `robo de vehículos Jalisco` | 0 |
  | `roban auto Jalisco` | 19 |
  | `"bases de datos"` | 53, casi todas basura |

- **Qué se concluye:**
  - Google News RSS no busca como el Google normal: exige todas las palabras y no reconoce sinónimos ni las formas de un verbo.
  - Rinden las frases **cortas y escritas como titular** («roban auto»). Los nombres de catálogo («robo de vehículos») casi no rinden.
  - Las comillas que el sistema ponía a cada frase de varias palabras (`quote`, ADR-0009) dejaban fuera casi todo.
  - Una frase genérica trae basura: el filtro de la IA sigue siendo necesario.
- **SearchApi `google_news`** raspa la pestaña Noticias de google.com (`tbm=nws`), según su documentación leída el 17/11/2026 (https://www.searchapi.io/docs/google-news). Ahí sí se ordena como en Google, pero cuesta 1 crédito por cada ~10 notas.

## Decisión

1. **Modo de búsqueda por concepto** (`concepts.query_mode`, migración 0046):
   - `exact` (como hasta hoy): cada frase entre comillas, unidas con OR.
   - `open` («como en Google»): hasta 12 frases (`OPEN_MAX_PHRASES`).
     - En Google News RSS cada frase va **sola y sin comillas**: `roban auto Jalisco when:7d`. Se parte por día si caben 12 consultas; si no, se manda una consulta por frase con la ventana completa.
     - Los proveedores sin tope de notas (SearchApi, BrowserWork) juntan las frases con OR y comillas, como siempre. Sin comillas, Google leería `(roban auto OR robo de vehículo)` como «roban» y («auto» o «robo») y «de» y «vehículo». Una frase que va sola sí sale sin comillas.
     - El lugar, la subdivisión y las exclusiones siempre van exactos: «Ciudad de México» sin comillas traería «Ciudad Juárez, México».
   - La búsqueda copia el modo en `search_concepts.query_mode`, para poder rehacer la consulta tal como se mandó.
2. **D2 — Lo que ya existe no cambia:**
   - Todos los conceptos actuales quedan en `exact`: la FGR, los 14 temas y los de cada analista. El monitor FGR y los envíos se buscan igual.
   - La API usa `exact` si no se dice otra cosa, para no cambiarle el comportamiento a quien ya la usa. El formulario manda `open` en los conceptos nuevos.
3. **D1 — La IA propone las frases:**
   - El analista escribe en sus palabras lo que busca, en la descripción.
   - La IA propone un nombre, de 8 a 12 frases tipo titular y hasta 6 exclusiones (prompt `terms_v1`, ruta `POST /concepts/suggest`).
   - No propone categoría: un concepto no tiene campo de categoría (solo los temas lo tienen). La categoría de cada nota la pone la IA al buscar, y se ve en las secciones de resultados (D5).
   - La propuesta no crea nada: el analista la revisa y la edita antes de guardar.
   - Cada propuesta queda en la bitácora (`concept.terms_suggested`), con su costo, aunque no se guarde el concepto. Medido con gpt-6-luna: ~0.0001 USD por propuesta.
   - Las frases son de 2 o 3 palabras, porque al buscar se les agrega el lugar. Medido el 17/11/2026 con 4 temas reales, en 7 días de Google News RSS:
     - con frases de 2 a 4 palabras: 508 notas distintas, y 5 de 39 frases trajeron 0;
     - con frases de 2 o 3 palabras: 641 notas distintas, y 2 de 40 frases trajeron 0.
   - El formulario va en dos pasos: «¿Qué noticias quieres seguir?» y luego las frases propuestas, ya editables. Se puede saltar la IA («Prefiero escribirlas yo»). Lo escrito en el primer paso queda como la descripción, que es contra lo que se juzga (D4).
   - Se llega desde Conceptos y, en el diseño clásico de Explorar, con «+ Nuevo concepto» junto a los conceptos: abre el formulario en una ventana y deja elegido el concepto al guardarlo. En el Centro de mando los conceptos se eligen en el selector del rediseño, que se coordina aparte.
4. **D4 — La IA juzga contra lo que se escribió:**
   - En los conceptos abiertos, la relevancia (prompt `enrich_v5`) se mide contra la descripción del analista. Las frases solo le sirven de pista.
   - Los conceptos exactos se le presentan a la IA igual que antes.
   - El tope de 150 notas por búsqueda (~0.20 USD) no cambia.
5. **D3 — Tope propio para las consultas gratuitas:**
   - El tope de 10 consultas por búsqueda (`MAX_QUERIES_PER_SEARCH`) cuenta solo las que cuestan créditos.
   - Las que van a un buscador externo gratuito (Google News RSS, BrowserWork, GDELT) tienen su propio tope: `MAX_FREE_QUERIES_PER_SEARCH`, 24 por defecto, que alcanza para dos conceptos abiertos.
   - El índice local no cuenta: es nuestra base y no la frena nadie.
   - Si una búsqueda pasa cualquiera de los dos topes, se rechaza antes de enviar nada. El mensaje dice qué tope pasó y cómo bajarlo («quita frases a los conceptos «como en Google»: cada frase es una consulta»).
   - Al RSS se le sigue pidiendo de 2 en 2 (`PROVIDER_MAX_CONCURRENCY`, sin cambio), con reintentos y espera cuando responde 429.
6. **D5 — Secciones por categoría:** la lista de resultados de Explorar se agrupa por las 15 categorías (ADR-0029), con su conteo. También en la pestaña «Noticias» del expediente del Centro de mando, que usa la misma lista. Las secciones se pliegan; con una sola categoría no hay secciones, porque cada tarjeta ya lleva su etiqueta. El filtro de colores del Centro de mando se queda.
7. **D6 — SearchApi sin gastar por ahora:** se queda como está. Usarlo de fijo se decide con un experimento de 3 créditos, solo si Benji lo aprueba.

## Alternativas consideradas

- **Quitar las comillas en todos los conceptos:**
  - Pros: un solo modo.
  - Contras: cambia el monitor FGR y los envíos de un día para otro, sin medirlo. «Fiscalía General de la República» sí conviene exacta.
- **Mandar el texto del analista tal cual a Google News RSS:**
  - Pros: no necesita IA.
  - Contras: medido, una palabra de más deja la consulta en 0 («hackeo bases de datos México»). El RSS no ordena como Google.
- **Usar solo SearchApi:**
  - Pros: es lo más parecido a Google.
  - Contras: 1 crédito por cada ~10 notas, con un tope de 100 al mes. Una búsqueda con 12 frases gastaría 12 créditos. Queda como experimento (D6).
- **Juntar las frases sin comillas con OR para gastar menos consultas:**
  - Pros: menos peticiones.
  - Contras: Google une el OR con la palabra vecina y no con la frase completa; además, las frases competirían por las mismas 100 notas del RSS.

## Consecuencias

- **Lo que se gana:** un concepto nuevo se escribe como se busca en Google y trae las notas escritas como titular, que son las que antes se perdían.
- **Más peticiones a Google News RSS:** hasta 12 por concepto en lugar de 4. No es un servicio oficial y puede frenar las peticiones. Se contiene con el tope por búsqueda y los reintentos del adaptador; si falla, la búsqueda queda parcial.
- **Más notas que leer:** con más notas, el tope de 150 de la IA se alcanza antes y algunas notas pueden quedar sin juicio. Se mide en la primera búsqueda real.
- **Las notas ya leídas se vuelven a leer una vez:** `enrich_v5` es otra versión del prompt, así que una nota leída con `enrich_v4` se paga de nuevo si vuelve a salir en una búsqueda (§10). Ya pasó con cada versión anterior. El costo sigue dentro del tope de 150 notas por búsqueda. En las corridas FGR la ventana es de unas horas, así que se espera que se repitan pocas notas.
- **Google News RSS frena si se le pide mucho seguido:** el 17/11/2026, tras ~90 consultas en unos minutos, respondió 429 («demasiadas peticiones»). Una búsqueda con dos conceptos abiertos son 24, de 2 en 2. Se vigila con el tope propio de las consultas gratuitas (D3).
- **Cambia la especificación §7.2:** ya no es siempre una consulta por proveedor y concepto.
- **El índice local** sigue buscando cada frase seguida, igual que antes.
