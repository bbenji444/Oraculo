# ADR-0112: Buscar en todo el mundo, en español

- **Estado:** aceptado (18/11/2026, Benji: «construye lo de todo el mundo solo con noticias en español»).
- **Fase:** F12.

## Contexto

Benji (18/11/2026): «si yo, por ejemplo, hipotéticamente quisiera buscar bases de datos hackeadas, pero en todo el mundo, no tengo esa opción».

Toda búsqueda va atada a una región del catálogo (`searches.region_id` y `delivery_schedules.region_id` son obligatorios). La más grande era un país, y cada país filtra a los proveedores:

- Google News RSS usa la edición del país (`gl`, `ceid`);
- SearchApi usa `gl`;
- GDELT usa `sourcecountry`.

Si no se elige región, la pantalla pone México.

Antes de decidir se consultó la documentación de cada proveedor (18/11/2026):

| Proveedor | ¿Se puede pedir «sin país»? |
|---|---|
| GDELT DOC 2.0 | Sí. `sourcelang:` y `sourcecountry:` son operadores independientes; sin `sourcecountry` se busca en la prensa de todos los países. |
| SearchApi (`google_news`) | No. `gl` es opcional, pero sin él usa Estados Unidos («The default parameter `us` defines the country of the search»). |
| Google News RSS | Sin documentación oficial. Medido con una consulta gratis: no hay edición mundial y hay que elegir un país. Con «robo de vehículos» (3 días), la edición de Estados Unidos en español trajo 9 medios .mx, 5 .cl y 1 .es; la de México, 11 .mx. |

## Decisión

1. **«Mundo» es una región más, de un nivel nuevo `world`** por encima de los países. La migración 0048 agrega el valor al tipo `region_level` y una fila: `code = 'WLD'`, «Mundo», con alias «Todo el mundo» y «Global».
   - Es un nivel propio y no un país falso, para que lo que pide países no lo confunda con uno: el geolocalizador, el mapa del reporte y «¿qué hay en este punto?».
   - Al ser una región, funciona sin más cambios en el historial, los reportes, los envíos programados y la búsqueda rápida.
2. **Solo noticias en español**, como pidió Benji:
   - `CountryFilter.worldwide` le dice a cada proveedor que no filtre por país;
   - GDELT recibe solo `sourcelang:spanish`;
   - SearchApi (Google News) va sin `gl`, con `hl=es`. Google web (ADR-0115, posterior) sí lleva `gl=mx`: ahí `gl` es el país de quien busca y sin él traía muy pocos resultados;
   - Google News RSS usa la edición `US:es-419`, marcada `# VERIFICAR` porque no tiene documentación.
   - El índice local no exige ninguna palabra de lugar.
3. **Dentro y fuera:** en «Mundo» toda nota con lugar está dentro. Una sin lugar queda «Sin ubicación», como en un país. El reporte cuenta las notas por país y su mapa pinta los países, sin contorno.
4. **En la pantalla:**
   - «Dónde» lleva arriba dos botones: «México» (o el país elegido) y «Todo el mundo».
   - Con «Todo el mundo» no hay estados ni municipios que elegir.
   - La frase dice «Rastrear… en todo el mundo» y el globo se aleja a la vista que gira.
5. **Búsqueda rápida:** «en todo el mundo», «en el mundo», «a nivel mundial/global/internacional», «en todos los países», «mundialmente» o «globalmente» buscan en «Mundo».
   - Se reconoce sin la IA.
   - «Mundial» suelto no cuenta, porque es el de futbol.
   - Si el texto también nombra un lugar del catálogo, gana ese lugar.

## Alternativas consideradas

| Alternativa | Por qué no |
|---|---|
| Hacer `region_id` opcional («sin región = mundo») | Toca las tablas `searches` y `delivery_schedules`, los esquemas, el reporte y el globo, y un nulo no dice si se olvidó o se quiso el mundo. |
| «Mundo» como un país más (`level = 'country'`, `WLD`) | Saldría en la lista de países, el geolocalizador podría asignarlo a una nota y «¿en qué país cae este punto?» lo devolvería en el mar. |
| Español e inglés | Trae más notas, pero duplica las consultas y lo que lee la IA. Benji eligió solo español. |
| Varias ediciones de Google News RSS (México, España, Argentina, Estados Unidos…) | Más consultas por búsqueda para resultados muy parecidos (medido: cambian pocas notas entre ediciones). |

## Consecuencias

- El analista busca un tema en todo el mundo con un clic, o escribiéndolo en la búsqueda rápida.
- El costo por búsqueda tiene los mismos topes. Pueden llegar más notas a la IA, hasta su tope por búsqueda.
- El índice local solo guarda notas de México (ADR-0013), así que en «Mundo» aporta las de México.
- SearchApi no tiene «sin país»: en «Mundo» se comporta como la edición de Estados Unidos en español.
- La migración no se deshace del todo: PostgreSQL no permite quitar un valor de un ENUM. El `downgrade` borra la fila y deja el valor sin uso.
