# ADR-0110: Concepto en una pantalla y búsqueda rápida

- **Estado:** aceptado (17/11/2026, plan aprobado por Benji).
- **Fase:** F12.
- **Ajusta:** ADR-0109 (D1, el formulario en dos pasos y el selector de modo).

## Contexto

Benji probó en la VM el formulario de ADR-0109 (17/11/2026):

- Al tocar «Prefiero escribirlas yo» pasaba al segundo paso y no había forma de regresar.
- No entendía la diferencia entre «Como en Google» y «Frases exactas»: «se hizo medio tediosa esa parte y medio confusa».
- Pidió que bastara con escribir lo que se quiere buscar, y una búsqueda rápida, «como en el buscador de Google, para cuando no quieres tener un concepto definido».

## Decisión

1. **D1 — Formulario en una sola pantalla:**
   - Lo único obligatorio es «¿Qué noticias quieres seguir?».
   - «Proponer frases con la IA» llena las frases y el nombre ahí mismo, para revisarlos.
   - Si se guarda sin frases o sin nombre, la IA los propone al guardar (~0.0001 USD) y solo llena lo que falta: no pisa lo escrito.
   - Se quitó el selector de modo: todo concepto nuevo se busca «como en Google».
   - Los conceptos exactos que ya existían (FGR, subdivisiones) se editan igual, con una línea que dice que se buscan con frases exactas. La API sigue aceptando `query_mode`.

## Alternativas consideradas

- **Dejar los dos pasos con un botón «Regresar»:**
  - Pros: cambio mínimo.
  - Contras: sigue siendo un paso más, y no resuelve la confusión del selector.
- **Dejar el selector con una explicación más larga:**
  - Pros: el analista decide el modo.
  - Contras: es una decisión técnica que el analista no tiene por qué tomar. Lo exacto solo lo necesitan la FGR y las subdivisiones, que ya existen.

## Consecuencias

- Un concepto se crea con una frase y un clic.
- Desde la interfaz ya no se crean conceptos exactos. Si algún día hace falta otro, se crea por la API con `query_mode: "exact"`.
- Guardar sin frases cuesta una llamada a la IA y tarda unos segundos más.
