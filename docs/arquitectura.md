# Arquitectura

Resumen de cómo se arma el sistema. El detalle está en la [especificación](ESPECIFICACION.md) (sección 5) y en los [ADRs](adr/README.md).

## Piezas y cómo se conectan

```
 Navegador (Windows)
   │  http://localhost:8080
   ▼
 nginx ──────────────► frontend/dist  (React compilado)
   │  /api/*           geodata/output (PMTiles, /tiles/*, con Range)
   ▼
 API FastAPI (uvicorn, 127.0.0.1:8000)
   │            │
   │            └── encola tareas ──► Redis ◄── Worker Celery
   ▼                                              │
 PostgreSQL 16 + PostGIS ◄────────────────────────┘
```

En desarrollo, todo lo que está debajo del navegador corre en **Ubuntu dentro de WSL** ([ADR-0006](adr/0006-entorno-desarrollo-sin-docker.md)). WSL2 reenvía los puertos de `localhost` a Windows, por eso el navegador de Windows ve <http://localhost:8080>.

## Capas del backend (hexagonal, [ADR-0001](adr/0001-arquitectura-hexagonal-e-idioma.md))

Las dependencias apuntan hacia adentro: `api`, `worker` y `adapters` conocen a `application`; `application` conoce a `domain`; `domain` no conoce a nadie.

Ejemplo real de la Fase 0, el diagnóstico `GET /api/v1/health`:

| Capa | Pieza | Qué hace |
|---|---|---|
| `domain` | `SystemHealth`, `ComponentHealth` | Regla: el sistema está sano solo si **todos** sus componentes lo están. |
| `application` | `HealthProbePort` (puerto) | Contrato: "revisa un componente y dime cómo está". |
| `application` | `CheckSystemHealth` (caso de uso) | Revisa todos los componentes en paralelo, con límite de tiempo por componente. |
| `adapters` | `PostgresHealthProbe`, `RedisHealthProbe`, `CeleryWorkerHealthProbe`, `AppHealthProbe` | Saben hablar con cada tecnología y traducen sus errores a un resultado del dominio. |
| `api` | `GET /api/v1/health` | Llama al caso de uso y responde 200 o 503. |
| `main.py` | Raíz de composición | Crea las conexiones y conecta los adaptadores con el caso de uso. |

Gracias a esta separación, el caso de uso se prueba con revisores falsos (sin base de datos ni red) y cambiar una tecnología solo toca su adaptador.

## Frontend

React 18 + TypeScript. Las llamadas HTTP viven en `src/services/`, los datos del servidor se administran con TanStack Query (`src/hooks/`) y los componentes solo muestran.
