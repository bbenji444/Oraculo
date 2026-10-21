# ADR-0105 — Estatus legal y procedencia como campos de primera clase

- **Estado:** aceptado
- **Fecha:** 2026-10-21
- **Fase:** F9 (sub-fase 9.2)
- **Decide:** Benji (plan de las fases 9–11, §9.2, §9.7 y §9.10; plan de la 9.2 aprobado el 21/10/2026, con "vinculado a proceso")
- **Bloque:** ADR-0101 a 0105 de las fases 9–11

## Contexto

Las notas de seguridad hablan de personas con situaciones legales muy distintas: alguien "señalado" por una fuente, alguien "detenido", alguien "vinculado a proceso", la víctima, un testigo. Confundirlas en pantalla, por ejemplo mostrar a un señalado como si fuera culpable, es un daño real.

También hay que saber siempre **de dónde salió** cada dato. Hoy viene de una nota o de la IA; mañana vendrá de otras bases (ADR-0101).

## Decisión

1. **Estatus legal solo para personas** (CHECK `entities_legal_status_only_people`). Refleja lo que dice la nota, nunca una conclusión del sistema. Si la nota no lo dice, queda vacío.

   | Código | Se muestra como | Cuándo |
   |---|---|---|
   | `mentioned` | mencionado | Aparece sin más |
   | `alleged` | señalado | "Orden de aprehensión contra…", "señalado como…" |
   | `detained` | detenido | "Fue detenido" |
   | `charged` | vinculado a proceso | "Fue vinculado a proceso" (agregado en la 9.2: es frecuente y no es lo mismo que detenido) |
   | `victim` | víctima | "La víctima" |
   | `witness` | testigo | "Un testigo" |
   | `official` | funcionario | Servidor público que actúa en su cargo |

2. **"Culpable" no existe.**
   - No hay código para ello, y el CHECK de la base rechaza `culpable`, `guilty` o `convicted`, tanto en `entities.legal_status` como en `entity_mentions.legal_status_hint`.
   - Si algún día se necesita "sentenciado", se agrega con su propio ADR y su migración.
3. **Procedencia en cada dato:**
   - **mención:** dice qué modelo y qué versión del prompt la extrajeron (`extracted_by`, `prompt_version`), de qué noticia salió y con qué cita (`evidence_span`, máximo 300 caracteres, que sobrevive al borrado del texto de la nota, ADR-0015);
   - **vínculo:** dice su origen (`cooccurrence`, `llm` o `human`) y su confianza;
   - **revisión:** dice quién la hizo y cuándo (ADR-0104).
4. **Los códigos van en inglés y las etiquetas en español**, en `app/domain/investigation.py`. Las pruebas de integración verifican que cada valor del dominio pase el CHECK de su columna.

## Alternativas consideradas

| Alternativa | Por qué no |
|---|---|
| Texto libre para el estatus legal | Cada nota lo diría distinto y no se podría filtrar ni mostrar con colores consistentes; tampoco se podría prohibir "culpable". |
| Un tipo ENUM de PostgreSQL | El resto del esquema usa CHECK de texto (`articles`, `searches`); un ENUM es más difícil de cambiar en una migración. |
| Guardar solo la posición de la mención en el texto | El texto se borra a los 30 días; sin la cita, la evidencia desaparece. |

## Consecuencias

- **Visible siempre.** Cualquier pantalla o reporte de la Fase 9 debe mostrar el estatus legal con su etiqueta, para no confundir "señalado" con "culpable".
- **Cambiar la lista de estatus pide una migración y actualizar este ADR**, a propósito.
- **La extracción de la 9.4** (ADR-0103) devuelve exactamente estos códigos; un valor desconocido se descarta, no se guarda.
