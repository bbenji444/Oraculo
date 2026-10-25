# ADR-0025: Duplicados en tres niveles: misma URL, misma nota con otro link y mismo hecho

- **Estado:** Aceptado (niveles 1 y 2; el nivel 3 se implementa en F12.1c)
- **Fecha:** 24 de octubre de 2026
- **Fase:** F12.1b
- **Decide:** Benji («eliminar los duplicados en las búsquedas para no saturarnos de información innecesaria o repetida… sin descartar la opción de tener información importante»)

## Contexto

Medición del 24/10/2026 en la base de desarrollo.

**Índice local** (`news_index`, 77,513 notas, 368 MB; 169 MB son frases del cuerpo):
- La llave única era la URL **tal cual llegaba**, así que `https://razon.com.mx:443/a` y `https://www.razon.com.mx/a` contaban como dos notas: 1,333 sobrantes así.
- El mismo medio guardaba el mismo texto con otro link: variantes `%20` en la ruta, el mismo artículo con otros parámetros (`?artid=134358&cat=1` y `&cat=254`) y títulos de portada repetidos: 1,363 sobrantes.
- 73 «notas» tenían como título solo un emoji («🎦»).
- 2,847 notas son **sindicadas**: el mismo texto en dos medios (tiempo.com.mx y puentelibre.mx).
- Cuidado: GDELT le pone el título de la portada a artículos **distintos** («Inicio | Periódico CiudadCCS»). Mismo medio y mismo título no basta para saber que es la misma nota.

**Notas de búsquedas** (`articles`, 1,450 notas):
- `dedupe` solo comparaba dentro de una búsqueda; contra la base, solo por URL. Resultado: 9 pares de la misma nota guardada dos veces (link de Google News contra link del medio, o la copia que quedó al reparar el Mojibake).
- Mismo hecho, otro medio, otro título: 52 pares con parecido de trigramas ≥ 0.70 a ±2 días, casi todos del mismo hecho («Balacera en Iztapalapa deja dos muertos…» ×4). Entre 0.45 y 0.70 hay ~280 pares mezclados: unos son el mismo hecho («El Cromos» / «Comandante Cromo») y otros son falsos parecidos por el nombre del medio pegado al título.

## Decisión

### Nivel 1: misma URL
La huella de `news_index.url_hash` se calcula sobre la **URL canónica** (`canonical_url`: sin `www.`, sin puerto por defecto, sin parámetros de rastreo, sin AMP), igual que en `articles`.

### Nivel 2: la misma nota con otro link
- **Índice:**
  - No entra una nota si el **mismo medio** ya tiene el mismo `text_norm` **y el mismo cuerpo** (o los dos sin cuerpo) a ±3 días (`SAME_OUTLET_WINDOW`, `NOT EXISTS` con el índice nuevo `news_index_domain_published`, migración 0023).
  - Exigir el mismo cuerpo evita juntar artículos distintos con título de portada.
  - Un título necesita al menos 2 letras (`MIN_TITLE_LETTERS`).
  - La misma nota en **otro medio sí entra**: es otra fuente, y saber que dos medios lo publicaron es información.
- **Búsquedas:**
  - Antes de guardar en `articles`, cada nota se compara contra lo guardado con la **misma regla de `dedupe`** (título ≥ 0.9 de parecido y ±1 día). La base trae candidatas por trigramas (`articles_title_trgm`) y `match_known` decide.
  - Si coincide, se reutiliza la nota guardada, con su IA ya pagada (`reusable_for`), sus casos y su ubicación.
  - Si la guardada tenía link de Google News y la nueva trae el del medio, se cambia al del medio. Dentro de una búsqueda también gana el link del medio.
- **Lo ya guardado:** `make limpiar-duplicados`.
  - Sin opciones **no borra nada**: da conteos por motivo y 5 ejemplos (qué se borra y qué se queda).
  - Con `ARGS=--aplicar` pide «si» y borra del índice lo que sobra. En cada grupo se queda la nota con cuerpo y, si empatan, la más antigua. Después recalcula la huella canónica de las que se quedan, por lotes de 10,000.
  - **Solo toca el índice**, que sirve para buscar y no está ligado a casos ni a reportes. En `articles` no se borra nada (ver nivel 3).

### Nivel 3: mismo hecho en varios medios = una «historia» (F12.1c)
- **No se borra nada.** Cada nota recibe `story_id`, y el monitor y el reporte muestran una tarjeta por historia con «▸ +N medios».
- La regla se calibra con 5 ejemplos reales antes de aplicarse. Punto de partida:
  - quitar del título el nombre del medio;
  - parecido ≥ 0.70 → misma historia;
  - entre 0.45 y 0.70, solo si además coincide el lugar principal o un nombre propio poco común;
  - siempre a ±2 días.
- Los 9 pares repetidos de `articles` quedan juntos en una historia.

## Alternativas consideradas

| Alternativa | Por qué no |
|---|---|
| Unicidad por (medio, título) sin mirar el cuerpo | Juntaba artículos distintos con el título de la portada: con esa regla se borraban 287 notas de más. |
| Borrar también las sindicadas (otro medio, mismo texto) | Se pierde la información de qué medios lo publicaron; el nivel 3 las muestra juntas sin perderlas. |
| Fusionar físicamente los pares de `articles` | Una nota puede estar en casos, entidades y búsquedas; mover todo eso es riesgoso para 9 pares que la historia ya junta. |
| Comparar con embeddings desde el nivel 2 | Para «la misma nota» basta la regla de título de `dedupe`; los embeddings se consideran solo para el nivel 3, si la regla gratuita se queda corta, y con aprobación aparte por costo. |

## Consecuencias

- Al aplicar la limpieza, el índice pierde ~2,769 notas repetidas (3.6 %), y deja de crecer por repetidas: cada corrida de ingesta ya las descarta.
- Las búsquedas dejan de crear notas repetidas entre búsquedas y no le vuelven a pagar a la IA por ellas. Las corridas automáticas (F12.8) se benefician igual.
- Cada nota nueva del índice hace una consulta extra (por medio y fecha, con índice); el costo es menor que el de la inserción.
- Un medio que publique dos notas distintas con exactamente el mismo título, fragmento y cuerpo en 3 días se guardaría una vez; en la práctica eso es la misma nota.
