# Historial de cambios

Todos los cambios importantes de este proyecto se documentan aquí.

El formato sigue [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) y el proyecto usa [versionado semántico](https://semver.org/lang/es/): cada fase N cierra con la versión `v0.N.0`.

## [Sin publicar]

## [0.0.0] - 2026-10-15

### Agregado

- **Fase 0 — Cimientos.**
  - Entorno de desarrollo sin Docker, con los servicios nativos en Ubuntu dentro de WSL (ADR-0006). `make bootstrap` instala PostgreSQL 16 + PostGIS 3.6, Redis 8, nginx, uv y Python 3.12 con un script que se puede repetir.
  - Comandos `make up`, `down`, `status`, `logs`, `test`, `lint`, `format`, `migrate` y `frontend-build`.
  - Endpoint `GET /api/v1/health` con el estado de la API, la base de datos (versión y extensiones), Redis y el worker. Responde 200 si todo está bien y 503 si algo falla, con el detalle en español.
  - Página inicial "Estado del sistema" con semáforo por componente, actualizada cada 10 segundos.
  - Backend FastAPI con arquitectura hexagonal, configuración por variables de entorno, logs JSON, Alembic (migración inicial de extensiones) y worker Celery.
  - Frontend React 18 + TypeScript + Vite + Tailwind CSS v4, con ESLint, Prettier y Vitest.
  - nginx como punto de entrada único (<http://localhost:8080>): frontend, proxy a la API, teselas con Range y encabezados de seguridad.
  - `.gitattributes` que fuerza finales de línea LF (CRLF solo en scripts de Windows), `.editorconfig` y pre-commit.
  - ADRs 0001 a 0006, README de arranque desde cero y documentación de arquitectura.

### Cambiado

- Especificación v1.2: campo `aliases` en `regions`, filtro `sourcecountry` en GDELT, nota sobre los links de Google News RSS y entorno de desarrollo sin Docker.
