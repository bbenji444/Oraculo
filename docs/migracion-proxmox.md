# Migrar el monitor a la VM de Proxmox (F12.9)

Guía para mover el monitor de la PC de Benji a la máquina virtual de Proxmox, que está prendida las 24 horas. **Por qué importa:** si la PC se apaga, las corridas de las 07:00, 15:00 y 23:00 no ocurren y el índice local se queda con huecos (el 22/10/2026 solo entraron 803 notas). En el servidor eso deja de pasar.

Esta guía la preparó Claude Code el 26/10/2026 sin acceso a la VM: **ningún paso se ha ejecutado todavía**. Cada uno dice cómo comprobar que salió bien.

## 0. Antes de empezar

- La VM con Ubuntu 24.04 (la misma base que WSL), al menos **4 núcleos, 8 GB de RAM y 40 GB de disco**. Hoy la base pesa ~900 MB y crece ~10 MB al día con el índice local, que se limpia a los 90 días.
- Acceso por SSH a la VM y salida a internet (GDELT, Google News RSS, la IA).
- El código en `develop` subido a GitHub (`git push`, con el OK de Benji).

## 1. Respaldar en la PC

```bash
wsl make db-dump
```

Comprobar: aparece `backups/monitor_noticias_<fecha>.dump`, de ~330 MB.

## 2. Instalar en la VM

```bash
git clone <repositorio> monitor-noticias && cd monitor-noticias && git checkout develop
make bootstrap
```

`make bootstrap` instala PostgreSQL con PostGIS, Redis, nginx, uv, Node y las dependencias. Se puede repetir sin problema.

Comprobar: `make status` muestra los servicios instalados.

## 3. Copiar la configuración y los geodatos

- **`.env`:** copiarlo de la PC a la VM por SSH (`scp`), **nunca por chat ni por correo**. Revisar en `.env`:
  - `BROWSERWORK_BASE_URL`, si se quiere usar BrowserWork desde la VM;
  - `AUTOMATIC_RUNS_ENABLED=true` (es el valor por defecto);
  - `REPORTS_DIR`, si los PDF deben quedar en otra carpeta.
- **Mapas:** los PMTiles del mapa y las texturas de la Tierra están en `geodata/output/` (catálogo INEGI, mapa base, `earth_day` y `earth_night`) y no van en git. Hay dos caminos:
  - copiarlos de la PC (`scp -r geodata/output vm:monitor-noticias/geodata/`);
  - volver a generarlos con `make geo-load`, `make geo-basemap` y `make geo-earth` (tardan y descargan varios GB).

## 4. Restaurar la base

```bash
pg_restore --no-owner -h localhost -U monitor -d monitor_noticias monitor_noticias_<fecha>.dump
make migrate
```

Comprobar con `make db-shell`:

```sql
SELECT count(*) FROM articles;        -- las mismas notas que en la PC
SELECT count(*) FROM news_index;      -- el índice local
SELECT name, relevance_rule FROM concepts WHERE deleted_at IS NULL;  -- solo la FGR, fgr_federal
```

(Más detalle en `docs/base-de-datos.md`, «Migrar la base a otro servidor».)

## 5. Levantar y probar

```bash
make frontend-build
make up
make status
make corrida-fgr
```

`make corrida-fgr` pide «si». Comprobar:

- `make status` muestra API, worker, reloj y nginx corriendo, y `/health` en «ok»;
- la corrida termina con notas y deja su PDF en `data/reportes/`;
- en el navegador (`http://<vm>:8080`), Historial muestra «Monitor automático · corrida de las …».

## 6. Que arranque solo al reiniciar la VM

`make up` levanta los servicios, pero no sobrevive a un reinicio. Hay que crear un servicio de `systemd` que corra `make up` al arrancar, igual que BrowserWork en el servidor de Oráculo. **Queda por hacer con Benji en la VM.**

## 7. Apagar el monitor en la PC

Cuando la VM ya corra sola, en la PC:

```bash
wsl make down
```

Si no se apaga, las dos máquinas harían las mismas corridas y gastarían la IA dos veces. Para dejar la PC solo como entorno de desarrollo, se puede poner `AUTOMATIC_RUNS_ENABLED=false` en su `.env`.

## Riesgos

| Riesgo | Cómo se evita |
|---|---|
| Corridas dobles (PC y VM) | Paso 7: apagar el reloj de la PC o `AUTOMATIC_RUNS_ENABLED=false`. |
| El `.env` con las llaves se filtra | Copiarlo solo por `scp`; nunca subirlo a git (está en `.gitignore`). |
| La VM no tiene los mapas | Paso 3: copiar los PMTiles o regenerarlos. |
| La hora de la VM no es la de la CDMX | El reloj trabaja en UTC y convierte (ADR-0031); basta con que la VM tenga la hora UTC correcta (NTP). |
