# ADR-0110: Concepto en una pantalla y búsqueda rápida

- **Estado:** aceptado (17/11/2026, plan aprobado por Benji).
- **Fase:** F12.
- **Ajusta:** ADR-0109 (D1, el formulario en dos pasos y el selector de modo).

## Contexto

Benji probó en la VM el formulario de ADR-0109 (17/11/2026):

- Al tocar «Prefiero escribirlas yo» pasaba al segundo paso y no había forma de regresar.
- No entendía la diferencia entre «Como en Google» y «Frases exactas»: «se hizo medio tediosa esa parte y medio confusa».
- Pidió que bastara con escribir lo que se quiere buscar, y una búsqueda rápida, «como en el buscador de Google, para cuando no quieres tener un concepto definido».

## Decisión

1. **D1 — Formulario en una sola pantalla:**
   - Lo único obligatorio es «¿Qué noticias quieres seguir?».
   - «Proponer frases con la IA» llena las frases y el nombre ahí mismo, para revisarlos.
   - Si se guarda sin frases o sin nombre, la IA los propone al guardar (~0.0001 USD) y solo llena lo que falta: no pisa lo escrito.
   - Se quitó el selector de modo: todo concepto nuevo se busca «como en Google».
   - Los conceptos exactos que ya existían (FGR, subdivisiones) se editan igual, con una línea que dice que se buscan con frases exactas. La API sigue aceptando `query_mode`.
2. **D2 — Búsqueda rápida con un concepto oculto:**
   - `POST /api/v1/searches/quick` recibe el texto, la región, las fechas y las fuentes.
   - La IA propone las frases (`SuggestConceptTerms`, ~0.0001 USD, queda en la bitácora).
   - Se crea un concepto «como en Google» **oculto** (`concepts.is_quick`, migración 0047): lo escrito es lo que la IA juzga y las frases son las de la IA. Su color es el cian de la consola (`#00D2FF`). Si la IA no da nombre, se usa el texto.
   - Se lanza la búsqueda con `StartSearch`, con los mismos topes y revisiones que una normal.
   - Los ocultos no salen en `GET /concepts` ni ocupan el nombre: los índices parciales de la migración 0005 se rehicieron con `AND NOT is_quick`.
   - «Guardar como concepto» (`POST /concepts/{id}/keep`) lo vuelve normal. Si el nombre ya existe responde 409 y hay que cambiarlo antes.
3. **D3 — Dónde se ve:**
   - Una barra «Busca noticias como en Google…» arriba de la consulta: en la consola del Centro de mando y en el panel del diseño clásico (`QuickSearchBar`).
   - Usa las fechas y las fuentes de la consulta, y su lugar si el texto no nombra otro (D4). Sin lugar elegido, busca en México.
   - Con los resultados a la vista sale «Guardar como concepto». Solo en la búsqueda rápida recién lanzada: no se recuerda entre visitas.
4. **D4 — El lugar que nombra el texto manda** (Benji, 17/11/2026: «Antes, el lugar»):
   - La misma llamada a la IA que propone las frases dice qué lugar nombra el texto y, si es un municipio o ciudad, su estado (prompt `terms_v2`, campos `place` y `place_state`). No cuesta una llamada más.
   - `resolve_place` lo busca en el catálogo **solo por nombre o alias exacto**: un parecido no basta, porque buscar en el lugar equivocado es peor que buscar en el elegido. Con nombres repetidos («Cuauhtémoc» en CDMX y en Chihuahua) gana el del estado que dio la IA; sin estado, el más general.
   - Si lo encuentra, se busca ahí aunque se haya elegido otro lugar (lo escrito es lo último que dijo el analista), y la respuesta lo trae en `place_region`. La pantalla lo deja elegido en «Dónde» para que el mapa y la consulta digan dónde se buscó.
   - Si el texto no nombra lugar, solo dice «México» o el lugar no está en el catálogo, se busca en el lugar de la consulta.
   - Las frases siguen sin lugar (ADR-0109): el lugar lo pone la región, como en cualquier búsqueda.

## Alternativas consideradas

- **Dejar los dos pasos con un botón «Regresar»:**
  - Pros: cambio mínimo.
  - Contras: sigue siendo un paso más, y no resuelve la confusión del selector.
- **Dejar el selector con una explicación más larga:**
  - Pros: el analista decide el modo.
  - Contras: es una decisión técnica que el analista no tiene por qué tomar. Lo exacto solo lo necesitan la FGR y las subdivisiones, que ya existen.
- **Búsqueda rápida sin concepto (el texto viaja en la búsqueda):**
  - Pros: no deja conceptos ocultos en la base.
  - Contras: el juicio de la IA, `search_concepts`, `article_concepts`, los filtros y el historial se apoyan en conceptos. Habría que tocar todo el pipeline.
- **Para el lugar (D4), buscar el texto palabra por palabra en el catálogo sin la IA:**
  - Pros: gratis y sin cambiar el prompt.
  - Contras: hay localidades llamadas «Robo», «Violencia» o «Autos» y municipios con nombres comunes; sin entender la frase se buscaría en lugares que nadie pidió. La IA ya se llama para las frases, así que el lugar sale en la misma respuesta.
- **Para el lugar (D4), que el lugar elegido en «Dónde» gane sobre el del texto:**
  - Pros: respeta lo que se eligió con el mapa.
  - Contras: el lugar por defecto es México, que casi nunca se elige a propósito; fue justo el caso de «en Jalisco».
- **Crear un concepto normal con un nombre único («Búsqueda rápida 1»):**
  - Pros: sin migración.
  - Contras: llenaría la lista de conceptos y «¿Qué rastrear?» de búsquedas de un solo uso.

## Consecuencias

- Un concepto se crea con una frase y un clic.
- Desde la interfaz ya no se crean conceptos exactos. Si algún día hace falta otro, se crea por la API con `query_mode: "exact"`.
- Guardar sin frases cuesta una llamada a la IA y tarda unos segundos más.
- **Los conceptos ocultos se acumulan:** uno por búsqueda rápida. Son filas pequeñas y sus búsquedas los necesitan para el historial. Si estorban, se podrán borrar los que no tengan búsquedas.
- **Si la búsqueda se rechaza** (sin llave de la IA, tope de consultas o de créditos), el concepto oculto y la propuesta ya quedaron creados. No estorban, pero la propuesta sí se pagó.
- **Más peticiones a Google News RSS:** cada búsqueda rápida son hasta 12 consultas. Varias seguidas pueden hacer que responda 429 (ADR-0109).
- **Primera búsqueda rápida real (17/11/2026):** «robo de autos con violencia en Jalisco», sin lugar elegido (México), 7 días, solo fuentes gratuitas.
  - La IA propuso «Robo violento de autos» con 8 frases («roban autos», «asaltan automovilistas»…), ninguna con el lugar.
  - 57 notas, 0 créditos, 0.018 USD de IA. Ninguna nombra Jalisco en el título, y solo 2 quedaron relevantes, de Chihuahua y de la CDMX.
  - Conclusión: si el texto nombra un lugar, la búsqueda tiene que ir a ese lugar. De ahí sale D4.
- **La misma búsqueda con D4 (18/11/2026):** el mismo texto con México elegido, 7 días, solo fuentes gratuitas.
  - La IA dijo «Jalisco» y se buscó en Jalisco; la pantalla lo dejó elegido en «Dónde».
  - Fueron 10 consultas a Google News RSS, una por frase y todas con «Jalisco». Dieron 228 resultados y 93 notas: 66 en Jalisco y 17 de ellas de vehículos. Costó 0 créditos y 0.027 USD de IA.
  - Solo 1 quedó relevante: «Robo de Auto Termina en Enfrentamiento el Ocotlán, Jalisco» (N+). Las demás eran cateos y vehículos asegurados en Ocotlán, autos con reporte de robo o un robo fingido. El juicio del asunto principal (`enrich_v5`) las descarta con razón.
  - Las dos búsquedas rápidas anteriores salieron como una sola consulta de frases exactas unidas con OR. El worker de desarrollo corría desde el 14/11, antes de ADR-0109, y rehacía el plan con el código viejo. Al reiniciarlo se buscó «como en Google». **Al publicar hay que reiniciar el worker**, no solo la API.
- **El lugar del texto cambia la región elegida (D4):** si la IA entiende mal el lugar, se busca en otro sitio. Se ve porque «Dónde» cambia y la bitácora guarda el `lugar` de cada propuesta. Para buscar en otro lugar basta con no nombrarlo en el texto y elegirlo en «Dónde».
- **Bajar la migración 0047** vuelve normales a los ocultos: si alguno repite el nombre de otro vigente, hay que renombrarlo o borrarlo antes.
