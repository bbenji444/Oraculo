# nginx/

Configuración de nginx, el servidor web que une todo en un solo punto de entrada: <http://localhost:8080>.

| Ruta | Qué sirve |
|---|---|
| `/` | El frontend compilado (`frontend/dist`). |
| `/api/` | Reenvía a la API (uvicorn en `127.0.0.1:8000`). |
| `/tiles/` | Los PMTiles de `geodata/output/`, con soporte de peticiones Range ([ADR-0004](../docs/adr/0004-maplibre-globo-y-pmtiles.md)). |

| Archivo | Qué es |
|---|---|
| `monitor-noticias.conf.template` | El sitio. `make up` reemplaza `__PROJECT_ROOT__` por la ruta real y lo instala en `/etc/nginx/sites-available/`. |
| `encabezados-seguridad.conf` | Encabezados de seguridad, incluidos en cada bloque que los necesita. |
| `encabezados-reporte.conf` | Los de la vista del reporte en pantalla (`/api/v1/searches/{id}/report/view`): sin la política de contenido ni `X-Frame-Options`, que pone la API para dejarla incrustar solo en el monitor ([ADR-0111](../docs/adr/0111-reporte-en-pantalla.md)). |

Para revisar la configuración instalada: `wsl sudo nginx -t`.
