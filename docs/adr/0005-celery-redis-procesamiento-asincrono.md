# ADR-0005 — Celery + Redis para procesamiento asíncrono

- **Estado:** aceptado
- **Fecha:** 2026-10-15
- **Fase:** F0

## Contexto

Una búsqueda consulta varios proveedores, deduplica, extrae el texto de cada nota, la enriquece con un LLM y la geolocaliza.
Eso tarda decenas de segundos o más. La API no puede quedarse esperando: debe responder de inmediato con un identificador y dejar que la interfaz consulte el progreso por etapas.
Además, en la Fase 8 se planean búsquedas recurrentes programadas.

## Decisión

1. **Celery** como sistema de tareas en segundo plano: la API encola la búsqueda (`POST /searches` → `202 {search_id}`) y un **worker** la ejecuta.
2. **Redis** como intermediario (broker) de Celery y, además, como caché de consultas a proveedores.
3. El progreso se guarda en la base de datos (`searches.progress`), no en Redis, para que sobreviva a reinicios y quede en el historial.
4. Las tareas del worker solo invocan casos de uso de `application/` (ADR-0001); no contienen lógica de negocio.

## Alternativas consideradas

| Alternativa | Por qué no |
|---|---|
| `BackgroundTasks` de FastAPI | Corre dentro del proceso de la API: si se reinicia, se pierde la búsqueda; no hay reintentos ni reparto entre varios workers. |
| RQ (Redis Queue) | Más simple, pero con menos soporte para tareas programadas, límites de concurrencia y monitoreo. |
| Dramatiq / arq | Buenas opciones, pero menos conocidas; Celery es el estándar con más documentación y gente que lo sabe operar. |
| Cola en la propia base de datos | Evita Redis, pero se necesitaría Redis de todas formas para la caché, y agrega carga a PostgreSQL. |

## Consecuencias

- Hay dos procesos más que operar (Redis y el worker); `/health` reporta el estado de ambos.
- Celery no soporta Windows oficialmente: en desarrollo corre en Ubuntu dentro de WSL (ADR-0006).
- Celery Beat permitirá las búsquedas programadas de la Fase 8 sin cambiar de herramienta.
