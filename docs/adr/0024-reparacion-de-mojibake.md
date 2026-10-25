# ADR-0024: Reparación propia y conservadora del Mojibake, al entrar y en lo ya guardado

- **Estado:** Aceptado
- **Fecha:** 24 de octubre de 2026
- **Fase:** F12.1
- **Decide:** Benji («Quita lo del Mojibake, aparece tanto en el sistema como en los reportes»)

## Contexto

Algunos títulos se veían con «letras raras», en el monitor y en los reportes: `Maru seÃ±alÃ³ corrupciÃ³n…`, `"Liberen a JÃ¡uregui"… ChihuahuaðŸŽ¦`. Es **Mojibake**: texto UTF-8 que alguien leyó como Windows-1252, así que cada letra acentuada se volvió dos o más caracteres.

Medición del 24/10/2026 en la base de desarrollo:

| Tabla.columna | Con Mojibake | Total |
|---|---|---|
| `news_index.title` | 396 | 77,304 |
| `articles.title` | 5 | 1,450 |
| `article_texts.body` | 1 | 933 |
| Fragmentos, medios, resúmenes, menciones de lugar, frases del cuerpo | 0 | — |

- **Origen:** todo viene de **GDELT** (ngramas y GKG), y solo de cinco medios: tiempo.com.mx (264), puentelibre.mx (64), planoinformativo.com (37), nvinoticias.com (21) y hoytamaulipas.net (10). El RSS de los medios, Google News RSS y SearchApi llegaron limpios.
- **Dos variantes más difíciles**, ambas en hoytamaulipas.net:
  - GDELT cambió comillas tipográficas por rectas y con eso borró un byte: `Ã"rdenes` era «Órdenes» y `ðŸ"¸` era 📸.
  - Un «…» escrito en Windows-1252 pasó por un carácter de control: `Â…`.

## Decisión

1. **Función propia en el dominio:** `app/domain/text_repair.py` (`repair_mojibake` y `clean_text`). Revierte la lectura equivocada (Windows-1252 → bytes → UTF-8) **solo** en las secuencias que forman un carácter UTF-8 válido **y** creíble en una nota en español: letras latinas, comillas y guiones tipográficos, €, símbolos y emojis. Si el resultado sería cirílico, CJK o un carácter de control, la secuencia se deja como estaba. El texto correcto (`Peñón`, `«ADIÓS”»`) no cambia, y en un texto mitad roto solo se arregla la parte rota. Hasta 3 pasadas, para el Mojibake doble.
2. **Al entrar:** `RawArticle.create` (todos los proveedores: SearchApi, Google News RSS, índice local, BrowserWork cuando llegue) y `NewsItem.create` (toda la ingesta: GDELT y RSS de medios) limpian título, fragmento y medio con `clean_text`. Ninguna nota nueva entra rota.
3. **Lo ya guardado:** `make reparar-texto`.
   - Sin opciones **no escribe nada**: da conteos por tabla y 5 ejemplos reales.
   - Con `ARGS=--aplicar` pide escribir «si» y repara `news_index`, `articles` y `article_texts`, por lotes de 10,000 con cursor y un commit por lote.
   - Recalcula `title_norm` y `text_norm` con las mismas funciones que la ingesta, para que la búsqueda siga encontrando la nota.
   - No llama a ninguna API ni a la IA, y no borra nada. Se puede repetir: la segunda vez no encuentra nada.
4. **Emojis:** se conservan tal como los publicó el medio (`Chihuahua🎦`). Quitarlos de los títulos es una decisión aparte, pendiente de Benji.

## Alternativas consideradas

| Alternativa | Por qué no |
|---|---|
| Librería `ftfy` | Resuelve esto y más, pero es una dependencia nueva para un problema acotado a cinco medios. La función propia mide unas 100 líneas, tiene pruebas con los casos reales y no requiere aprobación de dependencias. Si aparecen variantes que no cubre, `ftfy` es el siguiente paso. |
| Reparar solo al mostrar (frontend y reporte) | Deja la base sucia; la búsqueda y la comparación de duplicados (F12.1b) seguirían viendo títulos rotos. |
| Descartar las notas de esos cinco medios | Se pierden notas válidas; tiempo.com.mx publica nota roja de Chihuahua. |
| Arreglarlo solo con SQL (`convert_from`/`convert_to`) | Falla con textos mitad correctos y mitad rotos, y con los casos de comillas rectas. |

## Consecuencias

- Las notas nuevas ya no traen Mojibake, de ninguna fuente.
- Tras `make reparar-texto ARGS=--aplicar`, el monitor y los reportes muestran los títulos corregidos. Las búsquedas guardadas en el caché de Redis pueden mostrar el título viejo hasta que caduquen (`QUERY_CACHE_TTL_HOURS`, 6 h).
- La regla de la comilla recta (`"` → «“» o «”») podría equivocarse en una letra rara; con los datos medidos acierta en todos los casos.
- Queda una nota del índice (#217) cuyo título es solo un emoji (`🎦`). Es basura del medio; se atiende en F12.1b (calidad y duplicados).
