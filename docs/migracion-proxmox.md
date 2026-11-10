# El monitor en la VM de Proxmox (F12.9)

El monitor corre en la máquina virtual **108 «noticias»** del Proxmox de Oráculo, que está prendida las 24 horas. **Por qué importa:** si la PC se apagaba, las corridas de las 07:00, 15:00 y 23:00 no ocurrían y el índice local se quedaba con huecos (el 22/10/2026 solo entraron 803 notas).

**Mudanza hecha el 07/11/2026** por Claude Code, desde la PC de Benji y por SSH. Esta guía dice cómo quedó y cómo repetirlo en otra VM.

## Cómo quedó

| | |
|---|---|
| VM | Ubuntu 24.04.5, 4 núcleos, 8 GB, 80 GB de disco |
| Red de la oficina | `192.168.0.42` (SSH, para administrar) |
| ZeroTier (`oraculo2server`) | `10.244.214.144` |
| El monitor | `http://10.244.214.144:8080`; desde la oficina, `http://192.168.0.42:8080` |
| Usuario | `noticias`; el proyecto está en `/home/noticias/monitor-noticias` (rama `develop`) |
| Arranque | Servicio de systemd `monitor-noticias`: corre `make up` al encender |
| Base de datos | En el **PostgreSQL general de Oráculo** (`192.168.0.20`, PostgreSQL 17.9), base `monitor_noticias`, usuario `monitor` (solo esa base). Entra en los respaldos del servidor general y se ve en DBeaver dentro de la conexión `postgres`. Desde el 07/11/2026 |
| Corridas y envíos | Prendidos en la VM. En la PC de Benji están apagados (`AUTOMATIC_RUNS_ENABLED=false`, `DELIVERIES_ENABLED=false`), así nunca corren doble |

En la VM, el `.env` agrega:

```
API_RELOAD=false          # la API no se reinicia sola
NGINX_LISTEN=0.0.0.0:8080 # se ve en la red de la oficina y en ZeroTier
NGINX_SENDFILE=on         # nginx manda los archivos sin copiarlos
ORACULO_URL=http://172.25.18.234  # botón «← Oráculo» del encabezado
AUTOMATIC_RUNS_ENABLED=true
```

El monitor no tiene inicio de sesión todavía: lo puede abrir cualquiera en la red de la oficina o en ZeroTier.

## Entrar a la VM

Desde la PC de Benji, con la llave SSH `~/.ssh/monitor_vm` (está en el WSL de la PC):

```bash
wsl ssh -i ~/.ssh/monitor_vm noticias@192.168.0.42
```

Para darle acceso a otra computadora, se le crea su propia llave y se instala con `ssh-copy-id`. La contraseña de la VM la escribe una persona, nunca Claude.

**Permisos:** el usuario `noticias` puede, sin contraseña, solo lo que necesitan `make up`, `make down`, `make status` y el servicio (`/etc/sudoers.d/monitor-noticias`). Para instalar programas, `sudo` pide contraseña.

## Operar

```bash
sudo systemctl status monitor-noticias     # ¿está corriendo?
sudo systemctl restart monitor-noticias    # reiniciar
make status                                # servicios y /health
make logs                                  # logs de la API, el worker y el reloj
```

**Actualizar el código es automático.** Cada 5 minutos, el temporizador `monitor-noticias-actualizar` revisa GitHub. Si `develop` tiene commits nuevos, `scripts/servidor/actualizar.sh` hace esto:

1. Si hay una corrida o búsqueda en marcha, espera a la siguiente revisión para no cortarla.
2. Baja el código e instala las dependencias que hayan cambiado.
3. Compila la pantalla aparte y la cambia de golpe, así que nunca queda sin página.
4. Migra y reinicia.
5. Revisa `/health`. Si no responde, regresa al código anterior.

Para ver qué hizo:

```bash
journalctl -u monitor-noticias-actualizar --since today
```

Así, lo que entra a `develop` se ve en la VM en 5 a 10 minutos. Si algún día cambian programas del sistema (no de Python ni de Node), hay que correr `make bootstrap` a mano, porque pide contraseña de administrador.

## La base en el servidor general (07/11/2026)

El 07/11/2026 la base pasó de la VM al PostgreSQL general de Oráculo (`192.168.0.20`) para entrar en sus respaldos. El monitor sigue corriendo en la VM 108; solo cambió dónde guarda los datos.

1. **En DBeaver, con la conexión `postgres` (superusuario):**
   - `CREATE ROLE monitor LOGIN PASSWORD '…'` y `CREATE DATABASE monitor_noticias OWNER monitor`. El usuario no es administrador: solo abre su base.
   - Dentro de esa base, `CREATE EXTENSION` de `postgis`, `pg_trgm` y `unaccent`. Solo un superusuario puede crearlas.
2. **La contraseña** la eligió Benji. La guardó en la VM con `~/guardar_clave.sh`, que la pide sin mostrarla y la deja en `~/.clave_bd_central` (permiso 600). Nunca pasó por el chat. Si se pierde, en DBeaver: `ALTER ROLE monitor PASSWORD '…'` y se vuelve a guardar.
3. **Copia de los datos:**
   - se detuvo el monitor, `pg_dump` de la base de la VM y `pg_restore --no-owner` en `192.168.0.20`;
   - resultado: 0 errores y los mismos conteos (4,229 notas, 165,214 del índice, 299,618 regiones, 40 tablas, migración 0037).
4. **En el `.env` de la VM** cambiaron solo `POSTGRES_HOST=192.168.0.20` y `POSTGRES_PASSWORD`. La copia anterior está en `.env.antes-servidor-general`.
5. **De reserva:** la base vieja sigue en la VM, sin conexiones. Para regresar: `cp .env.antes-servidor-general .env` y `sudo systemctl restart monitor-noticias`. Se puede borrar cuando el servidor general lleve unos días sin problemas.

La contraseña de ejemplo de `.env.example` es pública (el repositorio es público), así que no se usa en el servidor general.

## Repetir la mudanza en otra VM

Lo que se hizo el 07/11/2026, en orden:

1. **Acceso.** En la PC: `ssh-keygen` y `ssh-copy-id` (la persona escribe la contraseña). Para la instalación, un permiso temporal de `sudo` sin contraseña, que se quita al final.
2. **`make`.** Ubuntu no lo trae y `make bootstrap` lo necesita: `sudo apt-get install -y make`.
3. **Código.** `git clone --branch develop https://github.com/bbenji444/Oraculo.git monitor-noticias`. El repositorio es público.
4. **`.env`.** Copiarlo de la PC con `scp`, nunca por chat ni por correo, y agregar las variables del servidor (arriba).
5. **Instalar.** `make bootstrap` instala PostgreSQL 16 + PostGIS, Redis, nginx, Node 22, uv, Python 3.12 y las dependencias. Tardó ~10 min.
6. **Mapas.** `geodata/output` (1.5 GB, 799 archivos) no va en git. Se copió de la PC con `tar | ssh` y se comprobó que el tamaño fuera idéntico.
7. **Base.**
   - En la PC, `make db-dump` (579 MB); copiarlo con `scp`.
   - En la VM: `pg_restore --no-owner -h localhost -U monitor -d monitor_noticias <archivo>.dump`. Resultado: 0 errores. Los conteos coinciden con la PC (4,229 notas, 299,618 regiones, 32 búsquedas, migración 0037).
   - Copiar también `data/reportes` (los PDF) y corregir sus rutas en la base:
     ```sql
     UPDATE reports SET pdf_path = replace(pdf_path, '/mnt/d/Proyectos/Oraculo/monitor-noticias', '/home/noticias/monitor-noticias') WHERE pdf_path LIKE '/mnt/d/%';
     ```
8. **Levantar.**
   - `make frontend-build`.
   - `make instalar-servicio`: deja que nginx lea la carpeta (Ubuntu 24.04 cierra las carpetas personales y nginx respondía 403), instala el servicio y los permisos mínimos.
   - `sudo systemctl start monitor-noticias`.
9. **Relevo.** Prender `AUTOMATIC_RUNS_ENABLED=true` en la VM y apagarlo en la PC (más `DELIVERIES_ENABLED=false`), reiniciando las dos.
10. **Cerrar.** Borrar el permiso temporal de `sudo`.

## Riesgos

| Riesgo | Cómo se evita |
|---|---|
| Corridas o correos dobles (PC y VM) | En la PC, `AUTOMATIC_RUNS_ENABLED=false` y `DELIVERIES_ENABLED=false` |
| El `.env` con las llaves se filtra | Solo por `scp`; nunca en git (está en `.gitignore`) |
| La hora de la VM | El reloj trabaja en UTC y convierte (ADR-0031). La VM sincroniza la hora sola (NTP) |
| Cualquiera en la red ve el monitor | Pendiente: inicio de sesión con la integración a Oráculo |
