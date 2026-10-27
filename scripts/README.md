# scripts/

Scripts de apoyo al desarrollo. Corren en Ubuntu dentro de WSL (ver [ADR-0006](../docs/adr/0006-entorno-desarrollo-sin-docker.md)).

| Script | Qué hace | Cómo se usa |
|---|---|---|
| `dev/instalar_wsl.sh` | Instala PostgreSQL 16 + PostGIS, Redis, nginx, uv y Python 3.12; crea el usuario y las bases de datos. Se puede repetir sin romper nada. | `wsl make bootstrap` |
| `dev/servicios.sh` | Arranca, detiene y muestra el estado de todos los servicios (base de datos, Redis, API, worker y nginx). | `wsl make up`, `wsl make down`, `wsl make status`, `wsl make logs` |
| `dev/base_datos.sh` | Consola SQL y respaldos de la base de desarrollo ([guía](../docs/base-de-datos.md)). | `wsl make db-shell`, `wsl make db-dump` |
| `dev/comun.sh` | Funciones compartidas por los dos anteriores (mensajes, espera de servicios, carga de `.env`). No se ejecuta solo. | — |

Los PIDs y logs de la API y el worker se guardan en `~/.local/state/monitor-noticias/` dentro de Ubuntu (no en `D:`), porque leer un archivo de `/mnt/d` justo después de escribirlo llegó a devolver datos equivocados.

Todos se ejecutan desde la carpeta del proyecto. En PowerShell, `wsl` traduce la carpeta actual de Windows (`D:\...`) a la de Linux (`/mnt/d/...`).
