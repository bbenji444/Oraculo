# backend/

API (FastAPI) y worker (Celery) del monitor de noticias. Corre en Ubuntu dentro de WSL con Python 3.12 (ver [ADR-0006](../docs/adr/0006-entorno-desarrollo-sin-docker.md)).

## Estructura (arquitectura hexagonal, [ADR-0001](../docs/adr/0001-arquitectura-hexagonal-e-idioma.md))

| Carpeta | Qué hay | Puede depender de |
|---|---|---|
| `app/domain/` | Entidades y reglas puras. Sin frameworks. | nada |
| `app/application/ports/` | Interfaces (`Protocol`) que el núcleo necesita. | `domain` |
| `app/application/use_cases/` | Acciones completas (por ejemplo, revisar la salud del sistema). | `domain`, `ports` |
| `app/adapters/` | Implementaciones de los puertos con tecnología concreta (PostgreSQL, Redis, Celery...). | `application`, `domain` |
| `app/api/v1/` | Routers FastAPI delgados y esquemas de entrada y salida. | `application` |
| `app/worker/` | App de Celery y sus tareas. | `application` |
| `app/core/` | Configuración (variables de entorno) y logs JSON. | — |
| `alembic/` | Migraciones de esquema. | `core` |
| `tests/unit/` | Pruebas sin red ni base de datos. | — |
| `tests/integration/` | Pruebas contra PostgreSQL y Redis locales, en la base de pruebas. | — |

## Comandos

Desde la raíz del proyecto, en PowerShell:

```powershell
wsl make test      # pruebas (unitarias + integración) con cobertura
wsl make lint      # ruff + mypy
wsl make migrate   # aplica migraciones
```

Las dependencias se administran con [uv](https://docs.astral.sh/uv/): `pyproject.toml` declara los mínimos y `uv.lock` fija las versiones exactas.
El entorno virtual vive en `~/.venvs/monitor-noticias` dentro de Ubuntu (no en `D:`), porque leer miles de archivos pequeños a través de `/mnt/d` es lento.

Para agregar una dependencia (requiere aprobación si no está en la especificación, CLAUDE.md §3):

```bash
UV_PROJECT_ENVIRONMENT=~/.venvs/monitor-noticias ~/.local/bin/uv add <paquete>
```
