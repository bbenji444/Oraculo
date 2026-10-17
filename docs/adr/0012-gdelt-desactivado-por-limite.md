# ADR-0012 — GDELT desactivado mientras responda 429 de forma persistente

- **Estado:** aceptado
- **Fecha:** 2026-10-16
- **Fase:** F3
- **Decide:** Benji

## Contexto

GDELT DOC 2.0 es el proveedor gratuito de la especificación (§8). Su mensaje de rechazo dice: *"Please limit requests to one every 5 seconds"*. En las consultas reales aprobadas del 16 de octubre de 2026 nunca devolvió una nota:

- **Primeras pruebas (10:51–11:10):** 2 respuestas `{}` y 2 consultas rechazadas con 429, aun respetando la pausa de 5 s y esperando 70 s entre corridas.
- **Diagnóstico aprobado por Benji (11:49–11:53):** 3 consultas con un término general que **siempre** tiene notas en español, `timespan=1d`, al menos 20 s entre consultas, máximo 3 intentos y al menos 15 s de espera tras cada 429. El cliente se identificaba como `monitor-noticias/0.2.0`.

| # | Consulta | Intentos | Respuesta final | Duración |
|---|---|---|---|---|
| D1 | `gobierno sourcelang:spanish` | 429 · 429 · 429 | **Error 429**, sin respuesta | 69 s |
| D2 | `gobierno sourcelang:spanish sourcecountry:MX` | 429 · 429 · 200 | **`{}`** (2 bytes) | 64 s |
| D3 | `gobierno sourcelang:spanish sourcecountry:mexico` | 429 · 200 | **`{}`** (2 bytes) | 35 s |

Las respuestas grabadas están en `backend/tests/fixtures/providers/gdelt_diag_*.json`, y cada envío quedó en `provider_queries` (filas 7 a 9 de la base de desarrollo).

**Interpretación:**

1. **El límite no depende de nuestro ritmo.** La **primera** petición de cada corrida recibió 429, aunque llevaba 20 s o más sin pedir nada. Probablemente GDELT limita nuestra conexión o está saturado; desde aquí no se pueden distinguir esas dos causas.
2. **Un `{}` después de un 429 no significa "sin resultados".** "gobierno" en notas en español de un día tiene cientos de resultados, y aun así D2 y D3 llegaron vacías justo después de ser rechazadas.
3. **No se pudo medir** si `sourcecountry:MX` (FIPS) o `sourcecountry:mexico` (nombre) filtran bien: para eso D1 tendría que responder con notas.

## Decisión

1. **GDELT queda desactivado por defecto** (`GDELT_ENABLED=false`). Las búsquedas no lo consultan: perder de 35 a 70 s por consulta esperando un vacío no aporta nada. En producción la búsqueda depende de SearchApi (Google News RSS está fuera por el ADR-0011).
2. **Un `{}` recibido después de un 429 es falla**, nunca "sin resultados". El adaptador lanza `ProviderRateLimitError` y queda en `provider_queries` con `status = 'error'` y el motivo. Un `{}` sin 429 previo sigue contando como "sin resultados". (Las filas 8 y 9 se registraron como `ok` antes de esta regla; se dejan como evidencia histórica.)
3. **Criterio para proponer reactivarlo:**
   - `make gdelt-diagnostico` reintenta **solo D1, una vez al día** (hora de la Ciudad de México), sin confirmación porque Benji lo aprobó.
   - Si ya se envió ese día, no envía nada.
   - Cuando D1 responda **con notas reales en 2 días distintos**, se avisa a Benji y **él decide**. El comando nunca cambia `GDELT_ENABLED`.
   - Si D1 trae notas, la respuesta se guarda como fixture: será la primera evidencia real del formato de un artículo.
4. El cliente sigue identificándose y esperando al menos 15 s tras un 429. Cada intento fallido queda en el registro.

## Alternativas consideradas

| Alternativa | Por qué no |
|---|---|
| Dejarlo activo con un solo intento | Hoy casi siempre fallaría, y cada falla agrega espera a la búsqueda sin aportar notas. |
| Seguir insistiendo con más consultas | Puede empeorar el bloqueo; el propio aviso de GDELT pide moderación. |
| Escribir al contacto que GDELT da en su aviso | Decisión de Benji; queda abierta. |
| Ingerir los archivos GKG de GDELT en lugar de la API | Otra forma de integrarse (archivos cada 15 min, con temas y ubicaciones). Se documenta en "Pendientes y mejoras futuras" de la especificación para evaluarla después; no se implementa ahora. |

## Consecuencias

- Mientras GDELT esté apagado, una búsqueda depende solo de SearchApi. Si SearchApi falla, la búsqueda no tiene proveedor.
- El formato de un artículo de GDELT sigue sin confirmarse con datos reales (`VERIFICAR` en `gdelt.py`).
- Si el criterio se cumple y Benji lo aprueba, basta con `GDELT_ENABLED=true`; si cambia la decisión de fondo, se crea un ADR nuevo.
