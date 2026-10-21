# ADR-0104 — Confirmación humana obligatoria

- **Estado:** aceptado
- **Fecha:** 2026-10-21
- **Fase:** F9 (sub-fase 9.2; se aplica en 9.4 y 9.5)
- **Decide:** Benji (plan de las fases 9–11, §9.4 y §9.8; plan de la 9.2 aprobado el 21/10/2026)
- **Bloque:** ADR-0101 a 0105 de las fases 9–11

## Contexto

La IA va a proponer personas, organizaciones, lugares y vínculos a partir de las noticias (9.4), y el sistema va a sugerir fusiones de personas parecidas (9.5). Una IA puede:

- inventar un nombre;
- confundir a dos personas;
- tomar ruido por evidencia ("Morena", que salió de una nota tangencial).

En una herramienta que perfila personas, un error así no es un detalle visual: es atribuirle algo a alguien.

## Decisión

1. **Todo lo propuesto nace sugerido.**
   - Entidades y vínculos tienen `review_status` con tres valores: `suggested`, `confirmed` y `discarded`.
   - El valor por defecto en la base es `suggested`, y el dominio lo fija en `INITIAL_REVIEW_STATUS`.
   - No se usa el booleano `is_confirmed` del plan: con él no se puede descartar ni distinguir "no revisado" de "rechazado".
2. **Confirmar o descartar deja firma.** Fuera de `suggested`, la base exige `reviewed_by` y `reviewed_at` (CHECK `*_review_signed`). Además, cada decisión va a la bitácora (`entity.confirmed`, `entity.discarded`, `relationship.confirmed`…).
3. **Solo lo confirmado entra al muro** (9.6).
4. **Las fusiones nunca son automáticas.**
   - El sistema puede sugerir que dos entidades son la misma (trigramas ≥ 0.9 y alias en común, dentro de un caso); solo una persona fusiona.
   - Al fusionar, una entidad apunta a la otra con `merged_into` y se conserva su historial.
   - **Las personas nunca se fusionan de forma automática a nivel global.**

## Alternativas consideradas

| Alternativa | Por qué no |
|---|---|
| `is_confirmed` booleano (como decía el plan) | No distingue "sin revisar" de "descartado" ni guarda quién decidió. |
| Confirmar solo lo de alta confianza (≥ 0.9) | La confianza la pone la misma IA que puede equivocarse; el plan exige confirmación humana sin excepciones. |
| Fusionar homónimos exactos automáticamente | Dos personas distintas con el mismo nombre es lo más común en notas de seguridad; unirlas es inaceptable. |

## Consecuencias

- **Más trabajo para el analista.** Revisa cada sugerencia; la 9.4 tiene que hacer esa revisión rápida (confirmar varias a la vez, ver la evidencia junto a cada una).
- **Seguridad en la base.** Aunque una fase posterior se equivoque, la base no deja confirmar sin firma.
- **Trazabilidad.** El muro puede mostrar siempre qué propuso la IA y qué validó una persona.
