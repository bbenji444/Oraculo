# ADR-0030: Relevancia FGR federal: la IA dice quién actúa y el concepto FGR lleva su regla

- **Estado:** Aceptado
- **Fecha:** 26 de octubre de 2026
- **Fase:** F12.5
- **Decide:** Benji (plan F12 §4.5: «cuentan las noticias donde actúa la FGR federal… no cuentan las fiscalías estatales»)

## Contexto

En la búsqueda FGR del 24/10/2026 (189 notas), la IA marcó relevante casi cualquier nota que **menciona** a la FGR, porque el concepto solo tenía palabras clave:

- La fosa común de San Luis Potosí (nota 1382) quedó relevante (0.75). La actora es la Fiscalía General **del Estado**; la FGR solo mandó dos oficios.
- «Desecharían amparos contra Modalidad 40» (1385) y «Gracias, Pancho Garfias» (1413) también quedaron relevantes, aunque la FGR solo se nombra de pasada.

Escribir una descripción más estricta del concepto no alcanza:

- La caché (`StoredArticle.reusable_for`) no vuelve a juzgar una nota ya juzgada aunque cambie el concepto.
- Volver a leerlas completas cuesta unas 12 veces más que clasificarlas.
- El texto de las notas viejas ya se borró (se guarda 30 días).

## Decisión

1. **Quién actúa** se guarda en cada nota (`articles.authority`, migración 0027, con índice). Los valores son:
   - `fgr`: la FGR federal, el MP Federal, la AIC o una fiscalía especializada federal; o alguien queda «a disposición de la FGR»;
   - `fgr_mencion`: la FGR solo se nombra;
   - `estatal`: solo actúa una fiscalía estatal;
   - `otra`: otra autoridad, ninguna, o una fiscalía extranjera;
   - `sin_dato`: no se puede saber.
2. Lo responde la IA **en la misma llamada por lotes que la categoría** (prompt `classify_v2`), con título y resumen. Cuesta lo mismo que clasificar: ~0.03 USD por 1,450 notas.
3. **Regla por concepto** (`concepts.relevance_rule`): `general` o `fgr_federal`. La migración pone `fgr_federal` en el concepto «Fiscalia General de la Republica».
4. **Relevancia final:**
   - Es la de la IA, salvo que el concepto tenga `fgr_federal` y la nota sea `fgr_mencion`, `estatal` u `otra`. Entonces no es relevante y la razón es una frase fija («Actúa una fiscalía estatal, no la FGR.»).
   - Con `sin_dato` o sin clasificar se respeta la IA: nada se esconde por falta de datos.
   - Se calcula **al leer** (lista, filtros, agregados, CSV y PDF), con un solo fragmento SQL armado desde `app/domain/authority.py`. Lo que dijo la IA se conserva intacto en `article_concepts`.
5. **No se borra nada:** las notas estatales pasan a «No relevantes», con su razón.

## Alternativas consideradas

| Alternativa | Por qué no |
|---|---|
| Descripción estricta del concepto, sin más | No cambia las notas ya juzgadas (caché) y no se puede releer lo que ya se borró. |
| Nuevo prompt de enriquecimiento (`enrich_v3`) | Invalida la caché de todo y obliga a releer artículos completos: unas 12 veces más caro. |
| Sobrescribir `article_concepts.is_relevant` | Pierde el juicio original de la IA y se desincroniza si la nota se vuelve a enriquecer. |
| Regla fija en el código para «el concepto FGR» | Depende del nombre; con `relevance_rule` la regla es explícita y se puede poner a otro concepto. |
| Palabras clave («Fiscalía del Estado») | La fosa de SLP nombra a las dos fiscalías; hace falta saber quién actúa, no quién aparece. |

## Consecuencias

- **El monitor FGR y las corridas automáticas (F12.8)** solo cuentan lo que hace la FGR federal, porque usan el mismo concepto.
- **Las búsquedas FGR anteriores** mostrarán menos relevantes al volver a abrirlas, porque el conteo se calcula al leer.
- **Lo que no se resuelve aquí:** las columnas de opinión sobre una acusación de la FGR cuentan como `fgr`. Si estorban en el reporte, se separan después.
