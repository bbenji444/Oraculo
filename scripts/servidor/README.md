# scripts/servidor

Lo que solo se usa en el servidor (la VM de Proxmox), no en WSL. La guía completa está en [docs/migracion-proxmox.md](../../docs/migracion-proxmox.md).

| Archivo | Para qué |
|---|---|
| `monitor-noticias.service.template` | Servicio de systemd: levanta el monitor (`make up`) al encender la VM y lo baja al apagarla. |
| `instalar_servicio.sh` | Lo instala y habilita. Se corre una vez con `make instalar-servicio`. |

Para manejarlo después:

```bash
sudo systemctl status monitor-noticias
sudo systemctl restart monitor-noticias
```
