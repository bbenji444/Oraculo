# ADR-0010 — httpx2 para las llamadas HTTP externas y sus pruebas

- **Estado:** aceptado
- **Fecha:** 2026-10-16
- **Fase:** F3
- **Decide:** Benji

## Contexto

La especificación (§5.4) eligió `httpx` (asíncrono) + `tenacity` para hablar con los proveedores de noticias, y CLAUDE.md §7 pide probar los adaptadores con `respx`. Al planear la Fase 3 se encontró, el 16 de octubre de 2026:

- `httpx` no publica versión desde la 0.28.1 (6 de diciembre de 2024).
- Su continuación mantenida es **`httpx2`** (2.13.1, 23 de septiembre de 2026). Su página en PyPI la presenta como continuación del trabajo de Tom Christie y la comunidad de HTTPX, ahora a cargo de Pydantic, "so that users have a reliably maintained path forward". Se importa como `httpx2`.
- El proyecto **ya depende de `httpx2`**: Starlette 1.8 la usa en el cliente de pruebas de FastAPI (Fase 0).
- `respx` 0.23.1 (abril de 2026) solo simula `httpx` (requiere `httpx>=0.25`). Usarlo obligaría a instalar también la librería sin mantenimiento.
- `httpx2` trae `MockTransport`, comprobado en el entorno del proyecto junto con `AsyncClient`, `Timeout`, `Limits`, `HTTPStatusError`, `TimeoutException` y `TransportError`. Con él una prueba responde con un archivo grabado sin tocar la red.

## Decisión

1. Los adaptadores de proveedores usan **`httpx2.AsyncClient`**, con tiempo máximo explícito, límite de conexiones y reintentos con `tenacity`.
2. Las pruebas de adaptadores usan **`httpx2.MockTransport`**, que responde con las respuestas reales grabadas en `backend/tests/fixtures/providers/`. Ninguna prueba sale a internet ni gasta créditos (CLAUDE.md §7 sigue igual en el fondo; solo cambia la herramienta).
3. No se instalan `httpx` ni `respx`.

## Alternativas consideradas

| Alternativa | Por qué no |
|---|---|
| `httpx` 0.28.1 + `respx`, como decían los documentos | Dos librerías HTTP en el proyecto, una sin mantenimiento desde hace casi 2 años, solo para poder usar `respx`. |
| `aiohttp` + `aioresponses` | Otra pila distinta a la que ya usa FastAPI/Starlette; sin ventaja para este proyecto. |

## Consecuencias

- Cambian la tabla §5.4 de la especificación (v1.5) y CLAUDE.md §7 ("respx" → "`MockTransport` de httpx2").
- Si `httpx2` cambiara su API, el impacto queda acotado a `app/adapters/providers/http.py`, el único lugar que crea clientes HTTP.
