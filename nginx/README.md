# nginx/

Configuración de nginx, el servidor web que une todo en un solo punto de entrada: <http://localhost:8080>.

| Ruta | Qué sirve |
|---|---|
| `/` | El frontend compilado (`frontend/dist`). |
| `/api/` | Reenvía a la API (uvicorn en `127.0.0.1:8000`). |
| `/tiles/` | Los PMTiles de `geodata/output/`, con soporte de peticiones Range ([ADR-0004](../docs/adr/0004-maplibre-globo-y-pmtiles.md)). |

| Archivo | Qué es |
|---|---|
| `monitor-noticias.conf.template` | El sitio. `make up` reemplaza `__PROJECT_ROOT__` por la ruta real (y las demás marcas, ver abajo) y lo instala en `/etc/nginx/sites-available/`. |
| `proxy-api.conf` | Cómo se reenvía cada petición a la API: Host, IP real y encabezados `X-Oraculo-*`. Lo incluyen los bloques de `/api`. |
| `encabezados-seguridad.conf` | Encabezados de seguridad, incluidos en cada bloque que los necesita. |
| `encabezados-reporte.conf` | Los de la vista del reporte en pantalla (`/api/v1/searches/{id}/report/view`): sin la política de contenido ni `X-Frame-Options`, que pone la API para dejarla incrustar solo en el monitor ([ADR-0111](../docs/adr/0111-reporte-en-pantalla.md)). |

## Detrás del gateway de Oráculo

Oráculo abre el monitor en `/m/noticias/` y le reenvía cada petición ([ADR-0119](../docs/adr/0119-gateway-oraculo.md), [docs/gateway-oraculo.md](../docs/gateway-oraculo.md)). Dos variables del `.env` lo controlan:

| Variable | Qué hace |
|---|---|
| `ORACULO_GATEWAY_IPS` | IP del proxy de Oráculo (separadas por espacio). Solo a ellas se les cree la IP real del analista (`X-Forwarded-For`) y los encabezados `X-Oraculo-*`; a cualquier otro se le borran. |
| `GATEWAY_ONLY` | `si`: solo entran el gateway y la propia máquina; los demás reciben 403. `no` (por defecto): sigue el acceso directo. |

Las rutas que esperan a la IA o a un proveedor (reporte, vista del reporte, sugerencias de términos y envíos de prueba o reintento) tienen 240 s; el resto de `/api`, 60 s.

Para revisar la configuración instalada: `wsl sudo nginx -t`.
