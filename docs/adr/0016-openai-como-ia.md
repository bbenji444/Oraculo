# ADR-0016 — OpenAI como IA del enriquecimiento, elegible junto a Gemini

- **Estado:** aceptado
- **Fecha:** 2026-10-17
- **Fase:** F4
- **Decide:** Benji

## Contexto

La especificación (§5.4, §10) eligió Gemini 2.5 Flash para enriquecer notas: relevancia, resumen, evento y lugares. El adaptador de Gemini quedó hecho y probado (ADR-0015). Benji tiene crédito de la API de OpenAI y pidió usarlo.

La IA ya está detrás de un puerto (`LLMPort`), así que cambiar de proveedor es escribir otro adaptador.

Datos de la documentación de OpenAI, consultada el 17/10/2026:

- **Precios por millón de tokens** ([pricing](https://developers.openai.com/api/docs/pricing)):

  | Modelo | Entrada | Salida |
  |---|---|---|
  | `gpt-6-luna` | 0.10 USD | 0.50 USD |
  | `gpt-5-nano` | 0.05 USD | 0.40 USD |
  | `gpt-5-mini` | 0.25 USD | 2.00 USD |
  | `gemini-2.5-flash` (referencia) | 0.30 USD | 2.50 USD |
- **`gpt-6-luna`** ([modelo](https://developers.openai.com/api/docs/models/gpt-6-luna)): "nuestro modelo más eficiente para tareas enfocadas de alto volumen". Admite Structured Outputs y `reasoning.effort = none`.
- **Salida estructurada** ([guía](https://developers.openai.com/api/docs/guides/structured-outputs)):
  - **Petición:** `POST /v1/responses` con `text.format = {type: "json_schema", name, schema, strict: true}`.
  - **Respuesta:** el JSON llega en `output[].content[]` con `type = output_text`.
  - **Uso:** viene en `usage.input_tokens` y `usage.output_tokens`.

## Decisión

1. **`LLM_PROVIDER` elige la IA:** `openai` (por defecto) o `gemini`. Los dos adaptadores cumplen `LLMPort` y comparten el prompt versionado (hoy `enrich_v2`, ADR-0020) y la validación con Pydantic.
2. **OpenAI usa `gpt-6-luna`** (`OPENAI_MODEL`) con `reasoning.effort = none`. El razonamiento se cobra como salida y no hace falta para extraer datos. Costo estimado por nota: ~0.00035 USD (2,000 tokens de entrada y 300 de salida), unas 4 veces menos que Gemini.
3. **Sin SDK de OpenAI.** Se llama por HTTP con el cliente compartido (ADR-0010): tiempo máximo, reintentos ante 429 y 5xx, y la llave en el encabezado. No agrega dependencias.
4. **Esquema estricto escrito a mano.** OpenAI exige, en modo estricto, que todos los campos estén en `required`, `additionalProperties: false` y los nulos como `["string", "null"]`. La respuesta se valida igual con Pydantic.
5. **La llave la pone Benji en `.env`** (`OPENAI_API_KEY`), igual que las demás. Nunca va al código, a commits ni a registros.

## Alternativas consideradas

| Alternativa | Por qué no |
|---|---|
| Solo Gemini (como dice §10) | Benji ya tiene crédito de OpenAI; Gemini queda disponible con `LLM_PROVIDER=gemini`. |
| SDK oficial `openai` | Una dependencia más (y otro cliente HTTP); la API se usa con una sola petición que el cliente compartido ya resuelve. |
| `gpt-5-nano` (más barato) | La diferencia es mínima (~0.0001 USD por nota) y `gpt-6-luna` es la generación vigente. Se puede cambiar con `OPENAI_MODEL`. |

## Consecuencias

- Una búsqueda de 100 notas cuesta ~0.035 USD de IA con OpenAI (~0.14 USD con Gemini).
- **Elegir otro modelo:** basta con `OPENAI_MODEL` y sus precios en `.env`.
- **Cambiar de proveedor:** cambiar `LLM_PROVIDER` vuelve a pagar las notas ya procesadas, porque el modelo forma parte de lo que se registra.
