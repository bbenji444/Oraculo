# scripts/servidor

Lo que solo se usa en el servidor (la VM de Proxmox), no en WSL. La guía completa está en [docs/migracion-proxmox.md](../../docs/migracion-proxmox.md).

| Archivo | Para qué |
|---|---|
| `monitor-noticias.service.template` | Servicio de systemd: levanta el monitor (`make up`) al encender la VM y lo baja al apagarla. |
| `sudoers-monitor-noticias.template` | Permisos mínimos de administrador: solo lo que necesitan `make up` y el servicio. |
| `actualizar.sh` | Baja lo nuevo de `develop`, instala, compila, migra y reinicia; si `/health` falla, regresa al código anterior. No corta una corrida en marcha. |
| `monitor-noticias-actualizar.service.template` y `.timer` | Corren `actualizar.sh` cada 5 minutos. |
| `instalar_servicio.sh` | Instala el servicio y los permisos, y deja que nginx lea la carpeta. Se corre una vez con `make instalar-servicio`. |

Para ver qué actualizó:

```bash
journalctl -u monitor-noticias-actualizar --since today
```

Para manejarlo después:

```bash
sudo systemctl status monitor-noticias
sudo systemctl restart monitor-noticias
```
