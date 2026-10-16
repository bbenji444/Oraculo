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

## Geodatos (Fase 1)

```
INEGI (ZIP 2.9 GB) ──Range──► solo el marco integrado (249 MB) ─► geodata/raw/
Natural Earth ─────────────────────────────────────────────────► geodata/raw/
                     │ extracción con CRC verificado (disco de Linux)
                     ▼
        ogr2ogr → staging_geo → (normalize_name, ST_MakeValid, ST_PointOnSurface)
                     ▼
                 regions (PostGIS) ──► /api/v1/regions/*   (búsqueda, punto, jerarquía)
                     │
                     └─ tippecanoe ──► geodata/output/*.pmtiles ──► nginx /tiles/ (Range)
Protomaps (OSM) ── pmtiles extract ───► geodata/output/basemap_*.pmtiles     ──┘
```

- **Una sola normalización de nombres** (`app/domain/names.py`) para el cargador, el buscador y, en F4, el geocodificador ([ADR-0008](adr/0008-fuentes-y-procesamiento-de-geodatos.md)).
- **GDAL nunca lee de `/mnt/d`:** en WSL recibió bytes dañados. Todo se procesa en el disco de Linux y a `D:` solo se copian resultados verificados.
- **El navegador nunca baja GeoJSON pesados:** las formas llegan por PMTiles; la API solo entrega punto y rectángulo.

## Frontend

React 18 + TypeScript. Las llamadas HTTP viven en `src/services/`, los datos del servidor se administran con TanStack Query (`src/hooks/`) y los componentes solo muestran.

El globo usa MapLibre GL JS v6 con proyección `globe` ([ADR-0007](adr/0007-maplibre-v6.md)). Su estilo (`src/map/style.ts`) es una función pura y probada: mapa base de Protomaps en español y capas de INEGI encima, con resaltado por `feature-state`.
