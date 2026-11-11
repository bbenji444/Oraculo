# Guía para conectar otro sistema con el monitor (llave de API por usuario)

Para el desarrollador que conecta el resto de Oráculo con el Monitor de Noticias. Diseño en ADR-0047.

## Qué es la llave

- Cada persona del monitor tiene **su propia llave de API**: `orc_live_<parte pública>_<secreto>`, de 58 caracteres.
- Con ella, tu sistema llama a la API del monitor **como esa persona**:
  - su rol (usuario o superusuario);
  - solo lo que ella puede ver (la base aplica seguridad por filas).
- La llave **no vence**. Deja de servir si:
  - el superusuario genera otra;
  - la persona se desactiva o se borra.

## De dónde sale

1. Un superusuario entra al monitor → pestaña **«Accesos»**.
2. En la persona, renglón **«Llave de API»** → **«Copiar»**. Si dice «Sin llave todavía», primero **«Generar llave»**.
3. Te la pasa por un canal privado (nunca por correo abierto ni en un chat de grupo).

## Cómo usarla

En **cada** petición, en el encabezado `Authorization`:

```bash
curl -s -H 'Authorization: Bearer orc_live_…' http://192.168.0.42:8080/api/v1/auth/me
# {"username": "ana.lopez", "display_name": "Ana López", "role": "user", ...}
```

- Base de la API: `http://192.168.0.42:8080/api/v1` (oficina) o `http://10.244.214.144:8080/api/v1` (ZeroTier).
- Documentación interactiva: `/api/v1/docs`, que también pide la llave.
- Referencia de rutas: `docs/api.md`.

Ejemplos:

```bash
# Las búsquedas de esa persona, la más nueva primero
curl -s -H 'Authorization: Bearer orc_live_…' 'http://192.168.0.42:8080/api/v1/searches?limit=5'
# Sus envíos programados
curl -s -H 'Authorization: Bearer orc_live_…' http://192.168.0.42:8080/api/v1/deliveries/schedules
```

## Reglas de seguridad (obligatorias)

1. **La llave es una contraseña.** Guárdala como secreto: variable de entorno, bóveda o tabla cifrada de tu lado. **Nunca** va:
   - en el código ni en Git;
   - en logs;
   - en el navegador (JavaScript, `localStorage`, URLs).
2. **Solo de servidor a servidor.** Si una pantalla de Oráculo necesita datos del monitor, la llamada la hace el backend de Oráculo, no el navegador.
3. **Siempre en el encabezado**, nunca en la URL (`?key=…`): las URLs quedan en historiales y logs.
4. **Una llave por persona.** No uses la llave de un superusuario para todo: se perdería la separación de quién ve qué.
5. **Si se filtra:** avisa al superusuario y que pulse **«Generar nueva»** en esa persona. La anterior deja de servir al instante.

## Qué responde si algo falla

| Código | Qué significa |
|---|---|
| `401 auth_required` | Falta la llave, está mal escrita, se reemplazó o la persona está desactivada |
| `403 forbidden` | La persona no tiene permiso para esa ruta (por ejemplo, un usuario normal en «Accesos») |
| `404` | No existe, o es de otra persona (la seguridad por filas lo oculta) |
| `429` | Demasiados intentos fallidos desde esa IP; espera unos minutos |

## Saber quién está detrás de una sesión del navegador

Para que otro módulo sepa quién es la persona del token de sesión del monitor (`monitor_sesion`), está `POST /api/v1/auth/introspect`. Lo usa una **llave de sistema de un superusuario**. Detalle en `docs/api.md`, sección «Acceso».
