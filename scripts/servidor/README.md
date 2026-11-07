# scripts/servidor

Lo que solo se usa en el servidor (la VM de Proxmox), no en WSL. La guía completa está en [docs/migracion-proxmox.md](../../docs/migracion-proxmox.md).

| Archivo | Para qué |
|---|---|
| `monitor-noticias.service.template` | Servicio de systemd: levanta el monitor (`make up`) al encender la VM y lo baja al apagarla. |
| `sudoers-monitor-noticias.template` | Permisos mínimos de administrador: solo lo que necesitan `make up` y el servicio. |
| `instalar_servicio.sh` | Instala el servicio y los permisos, y deja que nginx lea la carpeta. Se corre una vez con `make instalar-servicio`. |

Para manejarlo después:

```bash
sudo systemctl status monitor-noticias
sudo systemctl restart monitor-noticias
```
