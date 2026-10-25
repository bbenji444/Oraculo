# ADR-0027: Cada búsqueda manual elige sus fuentes con switches y las guarda

- **Estado:** Aceptado
- **Fecha:** 25 de octubre de 2026
- **Fase:** F12.2 (completa el ADR-0023)
- **Decide:** Benji («que nosotros podamos activar y desactivar mediante switches qué queremos buscar en cada búsqueda no automatizada»)

## Contexto

Hasta F12.1 una búsqueda consultaba **todos** los proveedores configurados en `.env`. El analista no podía, por ejemplo, buscar solo en fuentes gratis o probar una fuente nueva (BrowserWork, F12.3). La búsqueda tampoco guardaba con qué fuentes se hizo, así que el historial no lo decía.

El ADR-0023 ya fijó dos perfiles: el **automático**, fijo (Google News RSS e índice local, F12.8), y el **manual**, con switches. Este ADR decide cómo funciona el manual.

## Decisión

1. **Catálogo** en `app/domain/sources.py`:
   - Google News («gratis»), índice local («gratis») y SearchApi («créditos»).
   - GDELT queda fuera mientras siga apagado (ADR-0012).
   - BrowserWork entra en F12.3 agregando sus filas.
2. **Por defecto** se encienden las de `MANUAL_DEFAULT_SOURCES`, que hoy son las tres. SearchApi queda encendido como antes de F12.2 hasta que la medición de `make comparar-fuentes` diga cuánto aporta sobre el RSS; ese resultado se registra aquí y Benji decide.
3. **Reglas** (`resolve_sources`):
   - Si el analista no elige, se usan las de por defecto que estén configuradas.
   - Si elige, mandan las suyas.
   - Pedir una fuente no configurada, una que no se ofrece o ninguna responde `422` con un mensaje para el analista. No se planea nada ni se gasta.
   - Sin ningún proveedor configurado, el sistema sigue respondiendo «no hay proveedores disponibles» (503), como antes.
4. **La búsqueda guarda sus fuentes** en `searches.providers` (migración 0025):
   - El worker corre solo con esas fuentes.
   - `'{}'` en las búsquedas de antes de F12.2 significa «todas las configuradas», que es lo que hicieron.
   - La bitácora de auditoría registra `fuentes` (CLAUDE.md §8).
5. **El orden de las consultas** sigue siendo el de siempre (orden de `Provider`). El catálogo solo fija el orden en pantalla.

## Alternativas consideradas

| Alternativa | Por qué no |
|---|---|
| Elegir fuentes solo en el frontend, sin guardarlas | El worker volvería a usar todas, y el historial y la bitácora no dirían con qué se buscó. |
| Guardar las fuentes en `progress` (JSON) | `progress` es el avance de la corrida; una columna propia se lee y se audita más claro. |
| Ofrecer GDELT como switch | Está apagado por su límite (ADR-0012); encenderlo daría búsquedas fallidas. |

## Consecuencias

- Buscar solo con fuentes gratis cuesta 0 créditos, y la estimación lo muestra antes de buscar.
- El historial y la bitácora dicen con qué fuentes se hizo cada búsqueda.
- **Las corridas automáticas (F12.8)** usarán el mismo campo con su perfil fijo; no hace falta otro mecanismo.
- **Pendiente:** la medición RSS contra SearchApi (≤ 3 créditos, con aprobación) y, con ella, el valor por defecto de SearchApi.
