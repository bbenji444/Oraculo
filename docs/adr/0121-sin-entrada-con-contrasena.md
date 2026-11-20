# ADR-0121: Sin entrada con contraseña: solo por Oráculo con llave de API

- **Estado:** propuesto (20/11/2026).
- **Fase:** F12.
- **Reemplaza en parte:** ADR-0043 y ADR-0047 (entrar a la pantalla con usuario, contraseña y código de Microsoft Authenticator).
- **Relacionadas:** ADR-0119 (gateway de Oráculo), ADR-0120 (llave de API visible una sola vez).

## Contexto

Con el gateway (ADR-0119), Oráculo abre el monitor en `/m/noticias/` y manda en cada petición la llave de API de la persona. El usuario final ya no usa la contraseña del monitor. Benji, el 20/11/2026: «quiero que quites la opción de la contraseña. Va a estar abierto y solamente se van a comunicar los módulos mediante esta API».

Mientras siga la entrada con contraseña, hay un segundo camino para entrar que no pasa por Oráculo.

## Decisión

1. **Interruptor `PASSWORD_LOGIN`, apagado por defecto.** Apagado, la API no arma el ingreso con contraseña. Estas rutas responden 409 con «el acceso es por Oráculo con la llave de API»:
   - `POST /auth/login`, `/auth/login/password`, `/auth/login/enroll`, `/auth/login/enroll/confirm`, `/auth/login/code` y `POST /auth/password`;
   - en «Accesos»: `reset-password`, `reset-totp` y `PUT /access/settings`.
2. **La pantalla no ofrece contraseña.** `/app-config` responde `password_login`. Sin sesión, la pantalla muestra siempre «Tu acceso lo da Oráculo», también en el acceso directo. Se ocultan:
   - «Salir» y «Mi contraseña»;
   - el interruptor del código, «Contraseña temporal», «Sin Authenticator», «Restablecer contraseña» y «Reiniciar autenticador»;
   - el aviso de contraseña temporal al crear a alguien. Lo que sigue es «Generar llave».
3. **La identidad la dan solo las llaves** (`Authorization: Bearer orc_live_…`): la de API de cada persona, que Oráculo guarda y reenvía, o una de sistema (`make crear-llave`).
4. **No se borra el código de contraseña.** Queda detrás del interruptor (`PASSWORD_LOGIN=true`) por si hace falta volver; así el cambio es pequeño y reversible.

## Alternativas consideradas

- **Borrar todo el código de contraseña y Authenticator.**
  - Pros: menos código.
  - Contras: es un cambio grande con migraciones, y no hay vuelta atrás si Oráculo falla.
  - Se descartó por ahora: apagado por defecto tiene el mismo efecto.
- **`AUTH_MODE=dev` (sin candado).**
  - Contras: cualquiera en la red entra como superusuario. `make up` lo impide si el monitor se ve desde la red (ADR-0119).

## Consecuencias

- **El acceso directo** (`http://192.168.0.42:8080`) ya no sirve para entrar desde un navegador, porque el navegador no puede mandar la llave. Se entra por Oráculo; la API se sigue usando con Bearer.
- **«Accesos»** se usa entrando por Oráculo con la llave de un superusuario.
- **Primera llave del superusuario.** Si todavía no tiene una pegada en Oráculo: `make crear-llave ARGS="--usuario benji"` en la VM, que la muestra una vez, y se pega en Oráculo. Ya adentro, «Generar llave» en su renglón y se reemplaza.
- **Las sesiones abiertas antes del cambio** siguen hasta que caducan.
- **`make acceso`** (contraseña temporal por consola) solo sirve con `PASSWORD_LOGIN=true`.
