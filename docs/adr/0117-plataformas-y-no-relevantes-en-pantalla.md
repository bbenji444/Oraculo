# ADR-0117: Plataformas y «No relevantes» en pantalla

- **Estado:** propuesto (18/11/2026), falta el visto bueno de Benji.
- **Fase:** F12 (búsqueda «casi tan natural como Google», puntos 3 y 4, parte de la pantalla).

## Contexto

Benji comparó el monitor con Google (18/11/2026) y pidió dos cosas para la pantalla:

1. **Resultados fraccionados por plataforma**, como en Google: ver aparte lo de Facebook, X, YouTube, Instagram… y poder quedarse con una sola («solo Facebook», «solo X»).
2. **«No relevantes» que no sean basura total.** Medido en los juicios de la VM: 275 de 401 «no» de la IA tenían 0.2 o menos. El interruptor «No relevantes» las mostraba todas, mezcladas con las del mismo tema, y la razón de la IA llegaba a la API pero no se veía en ningún lado.

En paralelo, el servidor:

- calcula la plataforma de cada nota con una sola regla y la manda en `ArticleOut.platform` (valores: `news`, `facebook`, `x`, `youtube`, `instagram`, `tiktok`, `reddit`, `telegram`, `web`);
- agrega la búsqueda web de Google por SearchApi (`searchapi_web`, «Google web»), la única fuente que trae publicaciones de redes;
- manda la banda de cada juicio en `relevance_band`: `relevant` (0.8 o más), `unconfirmed` (0.6 a 0.79), `related` (0.3 a 0.59) y `unrelated` (menos de 0.3). `MIN_RELEVANCE_SCORE` sigue en 0.6 y hay una constante nueva, `MIN_RELATED_SCORE = 0.3`. Desde la revisión del 18/11/2026 (ADR-0114, sección 4), esas cuatro bandas son solo para los conceptos «como en Google» y la búsqueda rápida. En los exactos (el monitor FGR, los temas) el servidor manda `relevant` o `related`, así que sus no relevantes se ven con «Incluir las no relevantes», como antes, y no se esconden como ajenas.

Este ADR es solo la pantalla.

## Decisión

### Plataformas

1. **El filtro de plataforma vive con los demás filtros de la cronología** (`TimelineFilters.platforms`, `useTimelineStore.setPlatform` / `togglePlatform`). `applyTimeline` lo aplica, así el globo, la lista y la cronología muestran siempre las mismas notas. El campo es obligatorio para que TypeScript marque cada lugar que filtra. Se limpia solo en cada búsqueda nueva, como los demás.
2. **Pestañas tipo Google en el expediente** (`Mando/PlatformTabs.tsx`), entre «Cronología | Noticias» y «N de M notas · Filtro»: «Todo 42 · Noticias 35 · Facebook 5 · X 2…».
   - Se elige una a la vez: tocar otra deja solo esa y tocar la misma otra vez regresa a «Todo».
   - El conteo es facetado: respeta los demás filtros (fechas, categorías, estado y «Con/Sin ubicación»), «Incluir las no relevantes» y «Ver las … que descartó la IA», pero no la plataforma. Así cada pestaña dice cuántas notas vería. Lo arma una sola función (`platformFacet`, `Explore/timelineData.ts`) para el expediente, la ventana «Filtro» y el diseño de columna.
   - Solo salen las plataformas con notas, en orden fijo (no de más a menos, para que no brinquen de lugar). Si todo es de una sola, la fila no aparece; si la elegida se queda sin notas, la fila sigue para poder regresar a «Todo».
   - En celular la fila se desliza de lado, con pestañas de al menos 32 px de alto y un desvanecido a la derecha. En la computadora pasan a un segundo renglón, porque con el mouse no hay cómo deslizar una fila sin barra.
   - El diseño de columna (`?clasico`) lleva la misma fila arriba de la cronología o la lista.
3. **Sección «Plataforma» en «Filtro»** (`Mando/PlatformFilter.tsx`), antes de «Categorías», para elegir varias a la vez («Facebook y X»). Es el mismo filtro que las pestañas y cuenta con el mismo conjunto facetado, así la misma plataforma nunca sale con dos números distintos. El número del botón «Filtro» cuenta cada plataforma elegida y «Quitar filtros» también las quita.
4. **Marca por nota** (`Explore/PlatformMark.tsx`) en la lista, la cronología y la ficha del globo, solo en redes y otros sitios: las noticias de medios, casi todas, no la llevan para no meter ruido.
   - Junto a la marca, el nombre ya no repite la red: Google web dice «Facebook · Ignacio Gómez» y se muestra «Ignacio Gómez»; Google News dice «Facebook» a secas y no se repite.
   - En la ficha, el botón dice «Ver publicación en Facebook» (o en X, YouTube…) y «Ver página original» en otros sitios.
5. **Iconos de la letra Material Icons autoalojada**, revisados el 18/11/2026 leyendo sus ligaduras con fontTools: `newspaper` (Noticias), `facebook`, `smart_display` (YouTube), `photo_camera` (Instagram), `tiktok`, `reddit`, `telegram` y `language` (Otros sitios). La letra no trae X: va como una «X» en negritas. No se meten logos de las marcas en SVG.
6. **Si la API no manda la plataforma** (respuestas de antes o en caché), la nota se toma como noticia. Un valor que la pantalla no conoce se toma como «Otros sitios».

### «No relevantes»

7. **Bandas en pantalla** (`Explore/relevance.ts`):

   | Banda                      | Se ve                                                                     | Marca                                    |
   | -------------------------- | ------------------------------------------------------------------------- | ---------------------------------------- |
   | Relevante (0.8 o más)      | siempre                                                                   | ninguna                                  |
   | Por confirmar (0.6 a 0.79) | siempre                                                                   | «Por confirmar» y la razón de la IA      |
   | Cercana (0.3 a 0.59)       | solo con «Incluir las no relevantes»                                      | «Cercana» y «Por qué no: …»              |
   | Ajena (menos de 0.3)       | solo con el botón «Ver las 12 que descartó la IA», junto a «N de M notas» | «Descartada por la IA» y «Por qué no: …» |
   - Se usa la banda que manda el servidor. Si falta, se deduce del puntaje y de `is_relevant` con las mismas fronteras (`CONFIRMED_SCORE = 0.8` y `MIN_RELATED_SCORE = 0.3`, espejo del servidor). La pantalla no adivina más: la API no dice si la búsqueda fue literal, así que con un puntaje bajo la nota es ajena aunque la IA solo haya visto el título.
   - **Las ajenas no se esconden para siempre** (revisión del 18/11/2026). La IA casi siempre juzga solo con el título y el fragmento (`extraction_status = fallback`, porque los links de Google News no se resuelven) y así les pone 0.0–0.1 a notas correctas: las 6 que Google sí trae para «hacker Eternal» quedaban sin forma de verse. Van aparte del interruptor, para que «No relevantes» no vuelva a ser basura, detrás de un botón que las enseña con su marca y la razón, y que las vuelve a ocultar. El texto no dice que «no tratan del tema», porque con solo el título la IA se equivoca.
   - Si la IA solo vio el título, la marca de las cercanas y las ajenas lo dice al pasar el mouse: «La IA no pudo leer la nota completa: solo vio el título y el fragmento».
   - El botón se apaga solo al abrir otra búsqueda, al volver a una guardada y al limpiar el globo, como el interruptor.
   - Una nota es relevante si algún concepto la marcó relevante (`is_relevant`, que ya trae el umbral y la regla FGR). Una no relevante con puntaje alto, porque la quitó la regla FGR (fiscalía estatal), cuenta como cercana: es del tema, pero no lo que se pidió.
   - **Las notas que la IA no leyó** (pasaron del tope de notas o la IA falló) no tienen puntaje. No se esconden: salen con el interruptor, con la marca «Sin revisar». Esconderlas perdería notas que nadie juzgó.

8. **La razón de la IA se ve** en letra chica en la lista y en la ficha («Por qué no: es otro hackeo, no el de Eternal»). En la cronología va al pasar el mouse sobre la marca, porque su renglón no tiene lugar.
9. El botón de descartadas («Ver las N que descartó la IA» / «Ocultar las N…») va en el expediente, debajo de «N de M notas», y en la lista del diseño de columna. No aparece si no hay ninguna. La ventana «Filtro» explica bajo el interruptor que suma las cercanas y las que la IA no leyó, y que las descartadas se ven con ese botón.

## Alternativas consideradas

| Alternativa                                                      | Por qué no                                                                                                                                                                     |
| ---------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Calcular la plataforma en la pantalla, por la URL                | La URL de Google News es una redirección (`news.google.com/rss/articles/…`), y el reporte y el CSV necesitan la misma regla. Una sola regla en el servidor no se desincroniza. |
| Pestañas de varias a la vez                                      | Google elige una sola. Para varias ya está la sección «Plataforma» de «Filtro».                                                                                                |
| Agrupar la lista en secciones por plataforma                     | Ya se agrupa por categoría (ADR-0109 D5). Dos agrupaciones juntas no se leen; las pestañas y la marca bastan.                                                                  |
| Logos oficiales en SVG                                           | Implicaciones de marca registrada, y la letra ya trae casi todos. Si Benji quiere los logos, se decide aparte.                                                                 |
| Seguir mostrando todas las no relevantes con el interruptor      | Era la basura que Benji veía. Las ajenas van aparte, con su propio botón, para que se sepa que existen y se puedan revisar.                                                    |
| Esconder las ajenas sin manera de verlas (primera versión)       | Con solo el título la IA descarta notas correctas (el caso «hacker Eternal»). El analista tiene que poder revisarlas.                                                          |
| Tratar como «Sin revisar» las ajenas juzgadas solo con el título | Mezclaría con el interruptor justo las de puntaje más bajo, que en la mayoría sí son basura. El botón aparte las deja a un clic sin ensuciar «No relevantes».                  |
| Esconder también las que la IA no leyó                           | Sin puntaje no se sabe si son basura. Esconderlas callaría notas posiblemente útiles.                                                                                          |

## Consecuencias

- Hasta que el servidor mande Google web, casi todo dirá «Noticias» y la fila de plataformas no aparecerá. Hoy solo llegan unas cuantas de Facebook por Google News RSS (41 de 4,647 en la base de desarrollo).
- Las búsquedas viejas siguen funcionando: sin `platform` todo es noticia y sin `relevance_band` la banda sale del puntaje.
- Con «Incluir las no relevantes» se ven menos notas que antes: solo las cercanas. El analista sabe cuántas faltan por el botón «Ver las N que descartó la IA», y con él las ve.
- El estado del botón no suma en el número del botón «Filtro» ni lo apaga «Quitar filtros»: vive junto al conteo, que es donde se ve.
- El conteo «N de M notas» sigue contando todas las de la búsqueda (M), también las ajenas.
- Las bandas dependen de que la IA respete los rangos de puntaje del prompt. Si los cambia, se mueven las fronteras en el servidor y aquí (`relevance.ts`), en el mismo cambio.
- La prueba de humo usa tres notas hechas a mano (Facebook, YouTube y X), documentadas en `frontend/src/test/README.md`.
