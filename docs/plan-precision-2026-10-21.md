# Plan nocturno: búsqueda más amplia y ubicaciones precisas (21/10/2026)

Pedido de Benji (20/10/2026, noche):

- Al elegir varias notas de una misma zona, ver cuáles son y poder abrir cada una.
- "Ver nota original" debe abrir en otra pestaña.
- SearchApi debe traer al menos 3 páginas, sin gastar créditos de más.
- Menos notas sin ubicación y ubicaciones correctas.
  - Caso real: el homicidio del estilista de Micky Hair (Polanco, CDMX) aparecía en Jalisco.
- Más información útil para investigar.

Autorizado por Benji para ejecutarse sin esperar aprobación. El reporte se entrega al terminar.

## Diagnóstico con datos reales (5 búsquedas, 75 notas)

### Notas sin ubicación: 24 de 75

| Causa | Notas |
|---|---|
| La IA marcó todos los lugares como "mencionados", ninguno como "lugar del hecho" | 13 |
| El lugar del hecho no está en el catálogo (colonias, calles, "alcaldía X") | 9 |
| Páginas sin contenido ("Capital", "Zupralterno") | 2 |

### Menciones sin resolver: 140

De esas, 51 traen una palabra genérica al inicio ("alcaldía Miguel Hidalgo", "colonia Roma Norte", "calle Molière"). El catálogo busca el nombre completo y no las encuentra.

### Ubicaciones equivocadas

- **Polanco.**
  - La IA dijo "Polanco, Ciudad de México". INEGI no tiene colonias, así que no hay ningún Polanco en la CDMX.
  - El código descartaba entonces la pista del estado y se quedaba con cualquier "Polanco" del país.
  - Como la nota también nombra Jalisco, ganó una localidad de Jalisco.
- **Dos Bocas.**
  - La IA dijo que está en Tabasco.
  - Por la misma regla, terminó en Veracruz.

## Mejoras, en orden

### 1. Grupos de notas en un mismo lugar

- Al hacer clic en un grupo o en notas encimadas, aparece la lista de esas notas.
- Cada nota de la lista se puede abrir.

### 2. "Ver nota original" en otra pestaña

### 3. Fecha del hecho en la ficha

Ejemplo: "Hecho: 29 sep 2025 · nota del 16 oct 2026". Así se nota cuando la noticia es un avance de un caso viejo.

### 4. SearchApi con hasta 3 páginas

- Se pide la página siguiente solo si la anterior vino llena y Google ofrece otra.
- Cada página es una consulta exitosa, así que cuesta 1 crédito.
- La estimación muestra el máximo y la bitácora registra lo que se gastó de verdad.

### 5. Geolocalizador más preciso

- **a. Quitar palabras genéricas** antes de buscar: "alcaldía", "colonia", "calle"…
- **b. Respetar el estado que da la IA.** Un homónimo de otro estado nunca gana.
- **c. Catálogo de colonias de OpenStreetMap.**
  - Sale del mapa base que ya está descargado, sin bajar nada nuevo.
  - Aporta unas 22 mil colonias y zonas, con su punto y su alcaldía o municipio.
  - Polanco, Roma Norte, Condesa, Nueva Santa María y Granjas México ya aparecen ahí.
- **d. Pista de estado como último recurso.** Si nada más funciona, la nota se ubica en el estado que da la IA, marcada como aproximada (anillo punteado).
- **e. Ubicación principal.**
  - Se prefiere el lugar del hecho dentro de la región buscada.
  - Si la IA no marcó ningún lugar del hecho, se usa el lugar mencionado dentro de la región buscada, avisando que es un lugar mencionado.
- **f. Prompt v2 de la IA.** Ahora también pide la alcaldía o el municipio de cada colonia, calle o lugar.
  - Se vuelve a pasar el historial por la IA.
  - Costo aproximado: 0.05 USD para 75 notas.

### 6. Reubicar las 5 búsquedas y comparar antes y después

## Verificación

- Pruebas unitarias e integración de cada regla.
  - El caso Polanco y el de Dos Bocas quedan como pruebas que reproducen el error.
- Conteos antes y después en la base.
- 5 ejemplos reales.
- Capturas del globo.

## Resultado (21/10/2026)

Todo lo del plan quedó hecho y verificado. Commits en `feat/precision-y-paginacion`, sin subir.

### Historial de 5 búsquedas, antes y después

Notas distintas; reubicadas con las reglas nuevas y releídas con el prompt v2.

| | Antes | Después |
|---|---|---|
| Notas sin ubicación | 22 de 72 | 8 |
| Notas relevantes sin ubicación | 16 de 51 | 3 de 49 |
| Menciones sin resolver | 140 | 11 |
| Menciones ubicadas en su colonia | 0 | 29 |
| Homicidio · Miguel Hidalgo, notas dentro de la región | 0 | 12 |

- **Costo del reproceso:** ~0.026 USD de IA y 0 créditos.
- **Caso Micky Hair:** sus 5 notas quedaron en "Polanco, Alcaldía Miguel Hidalgo", dentro de la región.

### Búsqueda real nueva

Homicidio · Alcaldía Miguel Hidalgo · 7 días:

| | |
|---|---|
| Notas | 43 (antes 19 con 1 página) |
| SearchApi | 3 páginas, 30 notas, 3 créditos (bitácora) |
| IA | 0.0092 USD |
| Dentro de la región | 18 |
| Fuera de la región | 22 |
| Sin ubicación | 3 |

### Pendientes y límites conocidos

- **"Ajusco".** Si la nota solo trae título (sin texto completo), la IA no da municipio y gana la Colonia Ajusco de Coyoacán, en lugar de la zona del Ajusco en Tlalpan.
- **Fecha del hecho.** Cuando la IA solo sabe el mes, pone el día 1 ("1 sep 2025").
- **Ruido en las páginas 2 y 3.** Hay notas del Día de Muertos por la palabra "Muertos" del concepto Homicidio. El prompt v2 las marca como no relevantes, pero se pagan. Conviene agregar exclusiones al concepto.
- **Siguiente paso natural:** lugares de interés de OpenStreetMap (parques, plazas, hospitales) y calles.
