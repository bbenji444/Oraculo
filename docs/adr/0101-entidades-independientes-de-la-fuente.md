# ADR-0101 — Entidades independientes de la fuente y `external_links` reservada

- **Estado:** aceptado
- **Fecha:** 2026-10-21
- **Fase:** F9 (sub-fase 9.2)
- **Decide:** Benji (plan de las fases 9–11, Parte I; plan de la 9.2 aprobado el 21/10/2026)
- **Bloque:** ADR-0101 a 0105 de las fases 9–11 (`docs/PLAN_FASES_9-10-11.md`)

## Contexto

La Fase 9 agrega un tablero de investigación. En él, personas, organizaciones, lugares y vehículos se conectan entre sí sobre el globo.

- **Hoy** la única fuente de esas entidades son las noticias.
- **Mañana** habrá otras: las bases de datos reales del sistema Oráculo.

Si las entidades quedaran "dentro" de las noticias, conectar otra fuente obligaría a rehacer el tablero.

## Decisión

1. **Las entidades son objetos propios que tienen fuentes** (migración 0018):
   - `entities` es el objeto;
   - `entity_mentions` es una fuente: de qué noticia salió y con qué cita;
   - `relationships` une entidades, no noticias.

   El tablero solo lee entidades y vínculos; no sabe de dónde vinieron.
2. **Una fuente nueva es un adaptador nuevo**, igual que SearchApi lo fue para las noticias (ADR-0003). El tablero no se reescribe.
3. **`external_links` se crea, se documenta y se deja vacía:**
   - es el enchufe futuro de una entidad hacia un registro de otra base (`imss`, `repuve`…);
   - lleva `COMMENT ON TABLE` con esta regla;
   - ninguna lógica de la Fase 9 la lee ni la escribe;
   - `tests/unit/test_external_links_reservada.py` falla si algún archivo de `backend/app/` la nombra.
4. **Conectarla será una fase propia**, con su propio ADR que reemplace el punto 3. Antes hay que definir:
   - qué sistemas se conectan;
   - con qué base legal;
   - cómo se confirma una liga (nunca de forma automática, ADR-0104).

## Alternativas consideradas

| Alternativa | Por qué no |
|---|---|
| Entidades como columnas o JSON dentro de `articles` | Atan la entidad a la noticia: no hay forma de que una persona tenga menciones en varias notas ni de agregar otra fuente. |
| No crear `external_links` hasta que se use | El plan pide dejar el enchufe declarado para que el modelo no cambie de forma al conectarlo; crearla vacía cuesta poco y la prueba evita usarla antes de tiempo. |
| Crearla y llenarla con ligas sugeridas desde ya | Cruzaría datos personales con otras bases sin fase, sin base legal y sin confirmación humana. Prohibido por el plan. |

## Consecuencias

- **Lo que se gana:** las fases 9.3 a 9.7 trabajan con entidades sin importar la fuente, y el día que llegue otra base solo se agrega su adaptador.
- **Lo que cuesta:** la tabla existe vacía y una prueba de arquitectura vigila que siga así. Quien la necesite primero tendrá que cambiar este ADR.
