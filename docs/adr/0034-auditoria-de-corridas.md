# ADR-0034: Correcciones de la auditoría de las corridas FGR

- **Estado:** Aceptado
- **Fecha:** 27 de octubre de 2026
- **Fase:** F12
- **Decide:** Benji (27/10/2026: «haz un análisis de las corridas… detecta anomalías, repeticiones o cosas que estemos pasando por alto… encuentra errores, corrígelos»)

## Contexto

Se auditaron las 19 búsquedas guardadas y, a fondo, las 5 corridas del 26/10/2026 (03:45, 07:00, 11:29, 15:00 y 23:00). Con la base y con sondas gratis a Google News RSS se midió lo siguiente:

| Hallazgo | Medición |
|---|---|
| Google News salía de la caché | Las corridas de las 07:00 y de las 15:00 reusaron la respuesta de las 03:45 y de las 11:29 (caché de 6 h). No vieron lo publicado entre tanto. |
| Google News topaba | Cada respuesta trae a lo más 100 notas. La corrida de las 23:00 llegó justo a 100. |
| La palabra clave sin acentos | Entre comillas, «Fiscalia General de la Republica» trae 4 notas en dos días; «Fiscalía General de la República», 100 por día. |
| El índice local topaba | La corrida de las 23:00 llegó justo a 250, su máximo. |
| Cada corrida repite casi todo | 162 de las 172 notas de las 07:00 (94 %) ya venían en la corrida anterior; a las 15:00, 206 de 235 (88 %). El PDF no distinguía lo nuevo. |

Una sonda con 4 consultas gratis (nombre y sigla, cada día) juntó **281 notas distintas**; la consulta de siempre trajo 102. De las 181 nuevas, 108 son de dominios `.mx`, 70 de `.com` y solo 1 es extranjera (El Salvador). Son del tema: procesos, decomisos y aseguramientos.

## Decisión

1. **Google News RSS no pasa por la caché.** Es gratis; la caché existe para no gastar créditos (§7.2) y aquí solo envejecía los resultados.
2. **Google News RSS se parte** para no topar en 100. Se prueba, en este orden, lo que más notas trae sin pasar de 4 consultas por concepto:
   - cada palabra clave cada día;
   - las palabras juntas con OR, cada día;
   - cada palabra con la ventana completa;
   - las palabras juntas con OR (la regla de siempre).

   Solo se parte por día una ventana de fechas fijas de hasta 3 días: `when:Nd` («últimos N días») cuenta horas hacia atrás y no equivale a días de calendario. Con 4 consultas, un concepto y los otros 5 proveedores caben en el máximo de 10 por búsqueda. El texto de cada consulta lleva su día, pero el adaptador filtra con la ventana completa, porque Google no siempre respeta `after:`/`before:`.
3. **El concepto FGR lleva acentos** (migración 0031). Solo se cambia si sigue como lo dejó la semilla; `name_norm` no cambia, así que la corrida automática lo sigue encontrando. Lo que la IA ya juzgó se reutiliza: la caché de la IA depende de la versión del prompt y del concepto, no de sus palabras clave.
4. **El índice local devuelve hasta 500 notas.** Antes eran 250. El límite real es lo que la IA lee por búsqueda (150); lo que no alcanza a leer queda pendiente y lo lee la corrida siguiente.
5. **El PDF de una corrida automática separa lo nuevo de lo ya reportado** en la corrida automática anterior. Ver la sección «Novedades» del reporte.

## Alternativas consideradas

- **Bajar la caché de Google News a 30 minutos.** Se descartó: la consulta es gratis y tarda menos de 1 s, así que una caché solo agrega una forma de quedarse con datos viejos.
- **Partir por medio día.** Google News solo entiende fechas, no horas.
- **Sacar el enlace real del medio de las ligas de Google News.** Hoy 85 de las 338 notas del 26/10 (25 %) se guardan con la liga `news.google.com/rss/articles/…`. Por eso no se lee su texto completo, y su resumen, su ubicación y quién actúa salen solo del título. La única forma conocida de resolver esa liga es un servicio interno de Google sin documentación. Por la regla de no inventar APIs (CLAUDE.md §2.7), queda como decisión de Benji.

## Consecuencias

- Una corrida automática trae casi el triple de notas de Google News. La IA lee más notas nuevas: según lo medido el 26/10 (unos 0.00023 USD por nota), son unos **0.02 USD más por corrida** y **1.5 a 2 USD más al mes**.
- Una búsqueda manual de un concepto de 1 a 4 palabras clave usa hasta 4 consultas de Google News en lugar de una. Siguen siendo gratis.
- El número de notas por corrida sube. El reporte no crece igual, porque las del mismo hecho se juntan en una ficha (ADR-0026) y lo ya reportado se resume.
