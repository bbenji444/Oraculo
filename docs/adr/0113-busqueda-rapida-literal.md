# ADR-0113: La búsqueda rápida busca lo que escribió el analista

- **Estado:** aceptado (19/11/2026, Benji: «Sí, apruébalos»; propuesto el 18/11/2026).
- **Fase:** F12.
- **Ajusta:** ADR-0110 (D2, el nombre y las frases del concepto oculto los ponía la IA) y ADR-0109 (prompt `terms_v2`).

## Contexto

Benji buscó «Hacker Eternal» en la búsqueda rápida (18/11/2026) y salieron **0 notas**:

- La IA renombró la búsqueda a «Hackeo Eternal». Ese nombre salía en el Centro de mando y en el historial, así que el sistema parecía cambiarle la búsqueda.
- Sus frases eran variaciones de «hackeo», y algunas ya no llevaban «Eternal». Lo que Benji escribió nunca se mandó a Google.
- El juicio de relevancia (`enrich_v5`) no tenía forma de saber que una nota tenía que hablar de Eternal y no de cualquier hackeo.

El buscador de Google hace lo contrario: busca lo que escribiste, tal cual, y después te sugiere otras cosas.

Al revisar el pipeline apareció otro problema, sin relación con la IA:

- `searches` guarda solo las fechas. Una búsqueda manual de «últimos 7 días» llegaba al worker como un rango fijo.
- Por eso Google News RSS recibía `after:`/`before:`, que no respeta (medido el 16/10/2026), y SearchApi recibía fechas en vez de `time_period`.
- La vista previa (`/searches/estimate`) sí mostraba `when:7d`, así que la consulta que se veía no era la que se mandaba.

## Decisión

1. **El literal (`literal_phrase`, dominio, sin IA):** es el texto del analista listo para buscarse.
   - Se le quita la mención del lugar que se buscará y su preposición («en Jalisco»), porque el lugar ya lo pone la región. Si la preposición es «de» y la palabra anterior empieza con mayúscula, el lugar es parte de un nombre («Cártel de Sinaloa») y se queda.
   - Se le quita «en todo el mundo» (la expresión regular pasó de `quick_search` al dominio, `names_whole_world`) y las frases de tiempo obvias en las orillas («en los últimos 7 días», «esta semana», «hoy» al final). Las fechas ya las pone la consulta.
   - Se le quitan las comillas y los operadores (`OR`, `site:`, `when:`, paréntesis), para que el texto no rompa la consulta.
   - Se respetan las mayúsculas, los acentos y el orden. Si no queda nada que se pueda buscar (`is_searchable_term`), es `None`.
   - Ejemplos reales de la función: «Hacker Eternal» → «Hacker Eternal»; «robo de autos con violencia en Jalisco» → «robo de autos con violencia»; «bases de datos hackeadas en todo el mundo» → «bases de datos hackeadas»; «extorsión a comerciantes en los últimos 7 días» → «extorsión a comerciantes».
   - **Largo** (revisión del 18/11/2026, hallazgo 7): el tope del literal es de **palabras**, el de Google (`LITERAL_MAX_WORDS = GOOGLE_MAX_WORDS`, 32), no de 80 caracteres como una frase del formulario. «ataques de hackers a la Secretaría de la Defensa Nacional y a otras dependencias del gobierno federal mexicano» (110 caracteres) ya tiene literal. Además debe caber, solo, con el lugar, las exclusiones y el sufijo de fechas en la consulta de cada proveedor (`literal_fits`, `StartQuickSearch._fitting`); si no, `build_queries` rechazaría la búsqueda entera. `ConceptDraft.validated(..., literal_max_words=...)` acepta ese primer término solo cuando lo crea la búsqueda rápida.
   - **Texto mínimo** (misma revisión): en la búsqueda rápida basta un nombre, con al menos `QUICK_MIN_USEFUL_CHARS` (2) letras o números: «Pemex», «LockBit», «IA», «huachicol». Antes se pedían 10 caracteres, los mismos que en «Proponer frases con la IA» del formulario, que no cambia (`INTENT_MIN_LENGTH`).
   - **Cuándo no hay literal** y solo se buscan las frases de la IA (el nombre es el texto, recortado a 80 caracteres en un espacio):
     - si, sin el lugar, «en todo el mundo», las frases de tiempo y los operadores, no queda nada («en Jalisco», «en todo el mundo»), o queda una sola letra;
     - si pasa de 32 palabras;
     - si con el lugar, las exclusiones y «when:Nd» no cabe en la consulta de algún proveedor (por ejemplo, 31 palabras más «Jalisco» y «when:7d» pasan de 32).

     Si tampoco hay frases de la IA que sirvan, responde `422` («No se puede buscar ese texto tal cual…»).
   - **En SearchApi (Google News) el literal va entre comillas dentro del grupo con OR**, como frase exacta, y no como lo busca Google: así lo arma `query_builder` para todas las frases de un concepto abierto. Mandarlo sin comillas queda pendiente de medir (gasta créditos).
2. **El concepto oculto:**
   - **Nombre:** el literal, o el texto si no hay literal. La IA ya no le pone nombre a la búsqueda rápida; en «Proponer frases con la IA» del formulario sí lo sigue proponiendo.
   - **Palabras clave:** el literal primero. Después van las frases de la IA, sin repetir (comparadas con `normalize_name`) y con el tope de `OPEN_MAX_PHRASES` (12). Si una exclusión de la IA aparece dentro del literal, se descarta, porque si no la búsqueda se anularía sola.
   - Si no hay literal ni frases de la IA que sirvan, responde `422` con «No se puede buscar ese texto tal cual…».
3. **Prompt `terms_v3`** (`TERMS_PROMPT_VERSION = "terms_v3"`; `terms_v2.md` se queda como historial):
   - Tiene un campo nuevo, `entities`: los nombres propios, alias, grupos, siglas o marcas que escribió el analista, **copiados exactos** («"hacker" no es "hackeo"»).
   - Distingue dos casos:
     - un tema («robo de autos»), con frases como hasta ahora;
     - un sujeto con nombre («hacker Eternal»), donde **todas** las frases llevan el nombre.
   - Trae un ejemplo resuelto con «hacker eternal».
   - `TermsOut`, `TERMS_SCHEMA` (estricto, con `entities` en `required`), `TermSuggestionResult`, los adaptadores de OpenAI y Gemini y los dobles de prueba llevan `entities`.
   - Cambiar la versión no invalida ningún caché: la propuesta de frases no se guarda en caché.
4. **Los nombres propios se comprueban en el código (`literal_entities`):**
   - Solo se aceptan las entidades de la IA cuyas palabras normalizadas aparecen seguidas en el texto del analista, y se guardan con su ortografía, no con la de la IA. Así, si la IA se inventa o corrige un nombre, no pasa.
   - Hay un máximo de `MAX_REQUIRED_TERMS` (5).
   - **Un lugar no es entidad** (revisión del 18/11/2026, hallazgo 3; `without_places`): se quitan las entidades iguales (con `normalize_name`) al lugar que dio la IA y su estado (`SuggestConceptTerms`) y, en la búsqueda rápida, a los nombres del lugar resuelto en el catálogo: su nombre, alias, términos de búsqueda, su estado y su país (`place_names`). Si alguna sobraba, las frases de la IA se vuelven a limpiar con su respuesta original (`TermProposal.raw`). Antes, con «Jalisco» como entidad, el lugar quedaba protegido en el literal, se tiraban todas las frases de la IA y el juez exigía «Debe hablar de: Jalisco». Un nombre propio que solo lleva un lugar («Cártel de Sinaloa») se queda. `terms_v3` dice también que un lugar no va en `entities`.
   - `clean_suggestion` tira las frases de la IA que no llevan ninguna entidad. El literal nunca se tira.
   - La bitácora de la propuesta guarda las `entidades`.
5. **Términos obligatorios (migración 0049, no destructiva):**
   - Columnas nuevas: `concepts.required_terms` y `search_concepts.required_terms`, `text[] NOT NULL DEFAULT '{}'`. No llevan índice porque ninguna consulta filtra, une ni pagina por ellas.
   - Todos los conceptos que ya existían quedan con la lista vacía.
   - El dominio (`Concept`, `ConceptDraft`), la copia de la búsqueda (`SearchConcept`) y lo que recibe la IA al juzgar (`ConceptBrief`) llevan `required_terms`. Así el pipeline los tiene a mano.
   - Hoy solo los llena la búsqueda rápida. Editar el concepto desde el formulario no los borra (`ConceptChanges.apply_to` los conserva).
   - `ConceptOut` los expone **de solo lectura**.
   - El juicio (`enrich_v5`) y el filtro de relevancia **no** cambian en este ADR. Usar los términos para juzgar queda para después.
6. **«Últimos N días» de las búsquedas manuales (`manual_window`, sin migración):**
   - Al planear una búsqueda manual guardada, si la ventana termina hoy (Ciudad de México) y pasa de `SPLIT_MAX_DAYS` (3) días, vuelve a ser «últimos N días». Con eso:
     - Google News RSS recibe `when:Nd`.
     - SearchApi recibe `time_period` con 7 o 30 días. Con otros N sigue con fechas, porque SearchApi solo tiene `last_day`, `last_week` y `last_month`.
     - GDELT recibe `timespan`.
   - Las de 1 a 3 días se quedan fijas **a propósito**:
     - Las de 2 y 3 días se parten por día, y así traen más notas (medido el 27/10/2026).
     - «Hoy» con `when:1d` cuenta 24 horas hacia atrás, y podría llenar el tope de 100 notas con las de ayer, que después se tiran por la ventana estricta.
   - Las corridas automáticas (las que tienen `time_window`) siguen con sus fechas fijas.

## Alternativas consideradas

- **Pedirle a la IA que no cambie el texto, sin literal en el código:**
  - Pros: no hay que tocar el dominio.
  - Contras: así pasó «Hackeo Eternal». Un prompt no garantiza nada, y lo que escribió el analista tiene que buscarse siempre, aunque la IA falle o no responda.
- **Mandar el texto completo, sin quitarle nada:**
  - Pros: es lo más literal posible.
  - Contras: «robo de autos con violencia en Jalisco» buscaría «en Jalisco» dentro de la frase, y además la región ya pone «Jalisco»; «en todo el mundo» o «esta semana» achican los resultados sin razón. Lo que se quita es solo lo que ya ponen la región y las fechas.
- **Quitar el lugar con la IA (que devuelva el texto ya limpio):**
  - Pros: entiende casos raros.
  - Contras: es justo el paso donde la IA corrige palabras. El código solo quita el lugar que se resolvió en el catálogo y sus alias, nada más.
- **Confiar en las entidades de la IA tal como vienen:**
  - Pros: menos código.
  - Contras: la IA puede corregir la ortografía («Eternal» → «Eterna») o inventarse un nombre. Comprobarlas contra el texto es barato y no se equivoca.
- **Guardar «últimos N días» en una columna nueva de `searches`:**
  - Pros: no hay que deducir nada.
  - Contras: pide migración y cambiar el historial, los reportes y los envíos. Deducirlo de las fechas basta para el caso que importa, una búsqueda que se corre en cuanto se lanza.
- **Hacer relativas también las ventanas de 1 a 3 días:**
  - Pros: la vista previa y la corrida coincidirían siempre.
  - Contras: se pierden las notas que da partir por día, y «Hoy» traería las de ayer (ver D6).

## Consecuencias

- «Hacker Eternal» se busca tal cual:
  - en Google News RSS, como «Hacker Eternal when:7d»;
  - en SearchApi, como la primera frase del grupo con OR;
  - en Google web (ADR-0115), que manda la primera palabra clave, o sea, el literal.

  La búsqueda se llama así en el Centro de mando y en el historial.
- **Pruebas que cambiaron porque cambió el requisito** (no se debilitaron):
  - En `test_quick_search`, el nombre y la primera palabra clave del concepto oculto ahora son el texto, no lo que propuso la IA. `quick_name` recibe el literal.
  - La foto de la bitácora de un concepto trae `required_terms`.
  - Los dobles de la IA responden `terms_v3`.
  - La prueba de integración de `POST /searches/quick` espera el literal como nombre y como primera palabra clave.
  - Revisión del 18/11/2026: un texto de más de 80 caracteres ya tiene literal, así que `test_quick_search` y `test_term_suggestions` usan textos de más de 32 palabras para probar el caso sin literal.
- **Un literal de más de 80 caracteres queda en las palabras clave del concepto oculto.** Si después se guarda como concepto y se edita desde el formulario, el formulario pide acortarlo (su tope sigue en 80).
- **`required_terms` todavía no se ve en la pantalla del concepto** (revisión del 18/11/2026, hallazgo 3): el formulario no lo muestra ni lo deja editar. Con el candado de lugares ya no debería quedar un lugar ahí; mostrarlo queda pendiente del frontend.
- **Deducir la ventana depende de la hora:** si una búsqueda de «últimos 7 días» se lanza a las 23:59 y el worker la planea después de medianoche, ya no termina «hoy» y se busca con fechas fijas, como antes. No se pierde nada, solo se vuelve al comportamiento anterior.
- **La vista previa y la corrida siguen sin coincidir en 2 y 3 días:** la vista previa muestra una consulta con `when:2d` y la corrida manda una consulta por día. Es la misma diferencia que ya había.
- **Algunos literales quedan largos o raros**, por ejemplo «robo de autos de los más altos». Se buscan igual; las frases de la IA dan las variantes.
- **El literal ocupa uno de los 12 lugares de frases** (`OPEN_MAX_PHRASES`): si la IA propone 12, la última se queda fuera. Google News RSS no recibe más consultas que antes.
- **No se probó con la IA real:** hay que hacer una búsqueda rápida real con «Hacker Eternal» para ver qué entidades y frases da `terms_v3`. Al publicar hay que reiniciar la API **y el worker** (ADR-0110), y aplicar la migración 0049.
- **Bajar la migración 0049** borra los términos obligatorios de las búsquedas rápidas. Lo demás sigue igual.
