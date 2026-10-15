# ADR-0006 — Entorno de desarrollo sin Docker: servicios nativos en WSL

- **Estado:** aceptado
- **Fecha:** 2026-10-15
- **Fase:** F0
- **Decide:** Benji

## Contexto

La especificación original (v1.1) pedía un `docker-compose.yml` con postgres+postgis, redis, api, worker y nginx.
Al verificar el entorno de desarrollo se encontró:

- Docker no está instalado y el equipo tiene un problema conocido que impide usarlo.
- Windows 11 Pro **21H2** (build 22000). Docker Desktop exige Windows 11 23H2 (build 22631) o superior y WSL 2.1.5 o superior ([requisitos oficiales](https://docs.docker.com/desktop/setup/install/windows-install/)). Además es de pago para entidades de gobierno y empresas grandes.
- El WSL instalado es el integrado en Windows (no responde a `wsl --version`) y no arranca systemd, aunque `/etc/wsl.conf` lo pida ([documentación de systemd en WSL](https://learn.microsoft.com/en-us/windows/wsl/systemd)).
- Sí funciona WSL2 con **Ubuntu 26.04 LTS** (`resolute`), con 235 GB libres dentro de la distribución.
- Ubuntu 26.04 solo trae PostgreSQL 18 y Python 3.14; la especificación pide PostgreSQL 16 y Python 3.12.
- Varias piezas del proyecto no funcionan bien directamente en Windows: Redis no tiene versión oficial, Celery no soporta Windows oficialmente, WeasyPrint requiere GTK y tippecanoe no existe para Windows.

## Decisión

1. **Los servicios corren nativos en Ubuntu dentro de WSL**, sin contenedores:
   PostgreSQL 16 + PostGIS 3, Redis, nginx, la API (uvicorn) y el worker (Celery).
2. **PostgreSQL 16 se instala del repositorio oficial de PostgreSQL** (`apt.postgresql.org`, distribución `resolute-pgdg`), no del de Ubuntu, para respetar la versión de la especificación.
3. **Python 3.12 se instala con `uv`**, que además fija las versiones exactas de las librerías en `backend/uv.lock`. El entorno virtual vive en el disco de Linux (`~/.venvs/monitor-noticias`) y no en `D:`, porque leer miles de archivos pequeños a través de `/mnt/d` es lento.
4. **El código vive en Windows** (`D:\Proyectos\Oraculo\monitor-noticias`) y se edita con herramientas de Windows; git corre en Windows.
5. **El frontend (Node) corre solo en Windows** y el backend solo en Ubuntu. Las librerías de Node instaladas en un sistema traen binarios que no funcionan en el otro, así que nunca se mezclan.
6. **`make` corre en Ubuntu.** Desde PowerShell se usa `wsl make <comando>` en la carpeta del proyecto. Las tareas del frontend que lanza `make` (lint, pruebas, build) se ejecutan con el `npm` de Windows mediante la interoperabilidad de WSL.
7. **Un script idempotente** (`scripts/dev/instalar_wsl.sh`, invocado por `make bootstrap`) instala y configura todo. Se puede volver a correr sin romper nada.
8. **Sin systemd**, los servicios se arrancan con `service <nombre> start` y los procesos propios (api, worker) con archivos de PID en `.run/`.

## Alternativas consideradas

| Alternativa | Por qué no |
|---|---|
| Docker Desktop | No soporta Windows 11 21H2; licencia de pago para gobierno y empresas grandes. |
| Docker Engine dentro de WSL | Requiere actualizar WSL (`wsl --update`) para tener systemd; el equipo tiene un problema que impide usar Docker. |
| Todo nativo en Windows | Redis sin versión oficial, Celery sin soporte oficial, WeasyPrint frágil, tippecanoe inexistente. |
| VM Linux dedicada en Proxmox | Es la opción más limpia, pero depende de infraestructura que hoy no está disponible. Sigue siendo el destino recomendado para un servidor compartido. |
| Usar PostgreSQL 18 y Python 3.14 de Ubuntu | Más simple, pero se aleja de la especificación y del motor que ya usa el sistema principal (PostgreSQL 16). |

## Consecuencias

**Positivas**
- Más ligero que Docker: no hay capa de contenedores; Ubuntu ya estaba instalado.
- Las piezas que no funcionan en Windows (Celery, Redis, WeasyPrint, tippecanoe) corren en Linux real.
- Las versiones quedan fijas: PostgreSQL 16 del repositorio oficial y `uv.lock` para Python.

**Negativas y riesgos**
- Se pierde el aislamiento: los servicios quedan instalados en el Ubuntu de WSL. Si se rompe, se reinstala con `make bootstrap`.
- WSL puede apagar Ubuntu cuando no hay una terminal abierta, deteniendo los servicios. Se documenta en el README cómo comprobarlo.
- Los datos de PostgreSQL viven en el disco virtual de WSL, que está en `C:` (42 GB libres al momento de la decisión). Si los geodatos crecen, se puede mover la distribución a `D:` con `wsl --export` / `wsl --import`.
- Hoy Ubuntu entra como `root`; conviene crear un usuario normal más adelante.
- El despliegue final (F8) no queda atado a esta decisión: el código no depende de cómo se instalen los servicios, solo de las variables de entorno.

**Cambios derivados**
- Especificación v1.2: estructura del repositorio (5.3), tareas de F0 (17) y riesgo de entorno (19).
- `CLAUDE.md` §3 ("servicios de desarrollo" en lugar de "contenedores") y §7 (pruebas de integración contra una base de pruebas local separada).
