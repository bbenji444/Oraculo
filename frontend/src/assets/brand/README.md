# Marca de Oráculo

El logo del encabezado, copiado tal cual del sistema principal (Oráculo core)
para que el monitor se vea como sus demás módulos (ADR-0108).

| Archivo            | Origen                                                                                     | SHA-256                                                            | Tamaño     |
| ------------------ | ------------------------------------------------------------------------------------------ | ------------------------------------------------------------------ | ---------- |
| `oraculo-icon.svg` | Servidor OraculoApp, `webapps/oraculo/static/img/oraculo-icon.svg` (copiado el 17/11/2026) | `2a412dba3c1f9e9ba326d356b5bec393cd999bce6a85e7783f7a74e8d5cd7f72` | 1655 bytes |

Lo usa `App.tsx` (`OraculoBrand`). Si Oráculo cambia su logo, se vuelve a
copiar y se actualiza esta tabla.

Para revisar que el archivo no cambió:

```bash
sha256sum src/assets/brand/oraculo-icon.svg
```
