# ADR-0001 — Arquitectura hexagonal y convención de idioma

- **Estado:** aceptado
- **Fecha:** 2026-10-15
- **Fase:** F0

## Contexto

El sistema depende de servicios externos que cambian de precio, de API o desaparecen: proveedores de noticias (SearchApi, GDELT, Google News RSS) y modelos de lenguaje (Gemini).
La Custom Search JSON API de Google es un ejemplo real: cerrada a clientes nuevos y descontinuada el 1 de enero de 2027 (ver ADR-0003).
Además, el módulo se integrará después a un sistema mayor por API, y lo mantendrán personas que no participaron en su creación.

En cuanto al idioma, los usuarios, el responsable y la documentación son hispanohablantes, pero las herramientas, librerías y convenciones de código están en inglés.

## Decisión

**Arquitectura hexagonal (puertos y adaptadores)** en el backend, con las dependencias apuntando hacia adentro:

| Capa | Responsabilidad | Puede depender de |
|---|---|---|
| `domain/` | Entidades y reglas puras. Sin frameworks ni librerías externas. | Nada |
| `application/` | Casos de uso y **puertos** (interfaces `Protocol`). | `domain` |
| `adapters/` | Implementaciones de los puertos: proveedores, LLM, base de datos, caché, PDF. | `application`, `domain` |
| `api/` | Routers FastAPI delgados, esquemas de entrada y salida. | `application` |
| `worker/` | Tareas Celery que invocan casos de uso. | `application` |

**Convención de idioma:**
- En español: comunicación, documentación, docstrings, comentarios, mensajes de commit y textos de la UI.
- En inglés, sin acentos ni ñ: identificadores de código (variables, funciones, clases, tablas, columnas, endpoints).

## Alternativas consideradas

| Alternativa | Por qué no |
|---|---|
| Capas tradicionales (routers → servicios → modelos ORM) | La lógica de negocio termina acoplada al ORM y a los formatos de cada proveedor; cambiar de proveedor obliga a tocar el núcleo. |
| Todo en español, incluidos identificadores | Choca con librerías y frameworks en inglés, genera mezclas (`get_noticias`) y problemas con acentos y ñ en identificadores. |
| Todo en inglés | Los usuarios y el responsable trabajan en español; la documentación debe ser clara para ellos. |

## Consecuencias

- Cambiar de proveedor o de LLM significa escribir un adaptador nuevo, sin tocar `domain` ni `application`.
- La lógica de negocio se prueba con dobles de prueba (fakes) de los puertos, sin red ni base de datos. Esto permite exigir 85% de cobertura en `domain/` y `application/`.
- Hay más archivos e indirección que en una arquitectura en capas simple; se compensa con un `README.md` por carpeta.
- `mypy --strict` aplica a `domain/` y `application/` para proteger el núcleo.
