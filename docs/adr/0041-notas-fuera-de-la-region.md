# ADR-0041: Las notas fuera de la región no cuentan

- **Estado:** aceptada
- **Fecha:** 2026-11-09
- **Fase:** F12
- **Relacionadas:** ADR-0020 (reglas del geolocalizador), ADR-0038 (subdivisiones)

## Contexto

Benji buscó «PDI» y «Policía de investigación» en todo México y le salieron «muchas, pero muchas» notas de Chile. Revisamos esa búsqueda (09/11/2026):

| Ubicación de la nota | Notas |
|---|---|
| Chile | 47 |
| México | 34 |
| Sin lugar | 31 |
| Perú | 5 |
| Argentina | 2 |

Hubo dos causas:

1. **«PDI» es la Policía de Investigaciones de Chile.** Google News trae notas de toda Latinoamérica aunque se pida la edición de México.
2. **El sistema ya marcaba cada nota como dentro, fuera o sin lugar** (`search_results.in_region`), pero solo usaba esa marca en un filtro opcional. Las de fuera seguían en la lista, el globo, los conteos, el PDF y el resumen del correo.

Además, de las 31 «sin lugar», casi todas eran de medios chilenos (`adnradio.cl`, `chilevision.cl`, `cooperativa.cl`…).

## Decisión

1. **Por defecto, las notas fuera de la región no cuentan.** Afecta a la lista, el globo y el mapa de calor, los conteos por categoría, la vista previa, el PDF, el CSV y el resumen del correo.
   - Se aplica al leer (`_article_filters`, `in_region IS NOT FALSE`), así que también vale para las búsquedas pasadas.
   - Las notas se quedan guardadas: se ven pidiendo `in_region=false` (solo las de fuera) o `in_region=all` (todas).
2. **Una nota sin lugar de un medio de otro país cuenta como fuera.** El país sale de la terminación del dominio (`.cl`, `.pe`, `.ar`, `.co`, `.es`…; `outlet_country`). Los `.com` no dicen el país y se quedan «sin lugar». Esto aplica a las búsquedas nuevas, al cerrar cada búsqueda.

## Alternativas consideradas

- **Agregar «México» a cada consulta.** Se perderían las notas mexicanas que no dicen «México», que son la mayoría.
- **No guardar las notas de fuera.** Se pierde la posibilidad de revisarlas y auditar por qué se descartaron.
- **Solo un filtro más visible en la pantalla.** Benji espera que una búsqueda de México traiga México; el PDF y los correos no tienen filtro.

## Consecuencias

- Los conteos de búsquedas pasadas bajan: dejan de contar lo de fuera. Es lo que se busca.
- Una nota mexicana mal ubicada por la IA en otro país se oculta. Sigue visible con `in_region=false` y se corrige con `make reubicar`.
- Los medios con dominio `.com` de otros países siguen colándose cuando la nota no dice dónde ocurrió.
