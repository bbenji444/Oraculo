# ADR-0043: Entrar con contraseña y código de 6 dígitos; token interno

- **Estado:** aceptada (reemplaza la forma de entrar de ADR-0042; sus roles, RLS y llaves de sistema siguen)
- **Fecha:** 2026-11-10
- **Fase:** F12
- **Relacionadas:** ADR-0042 (llaves, roles y seguridad por filas), `docs/PLAN_AUTENTICACION.md`

## Contexto

ADR-0042 hizo que las personas entraran pegando una llave `orc_live_…`. Benji la probó y no le convenció, por tres razones:

- las llaves hay que generarlas a mano para cada persona;
- son incómodas de guardar;
- no se parecen a Oráculo.

En Oráculo se entra con usuario, contraseña y el código de 6 dígitos de Microsoft Authenticator, y la sesión no se cierra hasta que uno sale.

Benji pidió (10/11/2026):

- entrar **igual que en Oráculo**;
- que la contraseña genere un **token interno** que identifique a la persona y que después sirva para los **demás módulos**, sin pedir contraseña en cada uno.

Sus respuestas a las preguntas:

- **código de Microsoft Authenticator:** sí, igual que Oráculo;
- **duración de la sesión:** hasta que se dé «Salir», con un máximo de 30 días;
- **cuentas:** el superusuario las crea con una contraseña temporal.

## Decisión

### 1. Entrar en pasos

1. **Usuario y contraseña.** Si están bien, se abre un «ingreso a medias» en Redis que dura 10 minutos y dice qué falta.
2. **Solo la primera vez:**
   - cambiar la contraseña temporal por una propia;
   - dar de alta Microsoft Authenticator escaneando un QR;
   - el primer código confirma que el celular quedó bien.
3. **Código de 6 dígitos.** Con eso se abre la sesión.

### 2. Contraseñas

- **Se guarda la huella scrypt, nunca la contraseña.** Parámetros N=2¹⁵, r=8, p=1 (OWASP), con sal al azar. Revisar una contraseña tarda unos 96 ms en el servidor, a propósito, para que probar millones sea carísimo.
- **Reglas:**
  - de 12 a 128 caracteres;
  - letras y números;
  - no contener el usuario (si tiene 4 letras o más; con usuarios cortos como «ana» se rechazarían palabras como «mañana»).
- **Temporales:** 16 caracteres al azar, sin letras que se confundan al dictarlas. Se muestran una sola vez.
- **Bloqueos:**
  - 5 fallos seguidos bloquean la cuenta 15 minutos; pasado el bloqueo, se cuenta desde cero;
  - 10 fallos por IP en 15 minutos bloquean esa IP.
- **El mismo mensaje** si el usuario no existe, la contraseña está mal o la cuenta está bloqueada o desactivada. Aunque el usuario no exista se calcula scrypt, para tardar lo mismo.

### 3. Código de 6 dígitos (TOTP, RFC 6238)

- Es el mismo estándar que usan Microsoft y Google Authenticator: SHA-1, 6 dígitos, cambia cada 30 s.
- Se programó con la biblioteca estándar de Python y se comprobó con los vectores oficiales del RFC.
- Se acepta el código anterior y el siguiente (±30 s), por si el reloj del celular va desfasado.
- **Ningún código sirve dos veces.** Se guarda el último periodo usado y se actualiza de forma atómica en la base, así que dos peticiones simultáneas con el mismo código no pasan las dos.
- **El secreto va cifrado con AES-256-GCM.** La llave sale de `AUTH_KEY_PEPPER` con HKDF-SHA256. Si roban la tabla, no se pueden generar los códigos de nadie.
- El QR se dibuja en el servidor con `segno` y la pantalla lo muestra como imagen `data:`, que no puede ejecutar código.
- Un ingreso a medias admite 5 códigos equivocados. Después se cancela y hay que empezar de nuevo.

### 4. El token interno

- Al terminar el ingreso se abre una sesión en Redis. El navegador recibe su valor en la cookie `monitor_sesion` (`HttpOnly`, `SameSite=Strict`, `Path=/api`); en Redis solo se guarda su huella.
- La sesión dura hasta «Salir», con un tope de 30 días y sin cierre por inactividad.
- Cada 5 minutos se vuelve a revisar en la base que la persona siga activa y con el mismo rol.
- **Para los demás módulos:** `POST /api/v1/auth/introspect` recibe un token y responde de quién es (`active`, `username`, `display_name`, `role`).
  - Quien pregunta se identifica con una llave de sistema de un superusuario (`Authorization: Bearer orc_live_…`).
  - Así otro módulo de Oráculo sabe quién es la persona sin pedirle contraseña.

### 5. Administración («Accesos»)

- Dar de alta a una persona genera su contraseña temporal, que se muestra una sola vez.
- «Restablecer contraseña» le da una temporal nueva y cierra sus sesiones. Su Authenticator no cambia.
- «Reiniciar autenticador» borra su secreto y cierra sus sesiones. Al entrar escanea un QR nuevo.
- «Mi contraseña»: cada persona cambia la suya; se cierran sus demás sesiones.
- Las llaves `orc_live_…` quedan **solo para sistemas** («Llaves de sistema»).
- `make acceso ARGS="--usuario benji"` da una contraseña temporal desde la consola del servidor, para el primer superusuario o para recuperar el acceso.

### 6. Dependencias

- **`segno`:** dibuja el QR. Es Python puro y sin dependencias; Benji la aprobó el 10/11/2026.
- **`cryptography`:** cifra con AES-GCM. Ya venía instalada por `google-genai` y `composio`; se declara porque ahora el monitor la usa directamente.

## Alternativas consideradas

- **Seguir con llaves para personas.** Es incómodo y Benji lo rechazó.
- **Entrar con la cuenta de Oráculo (SSO).** Es lo ideal, pero hoy no hay acceso al código de Oráculo ni quien lo autorice. Este diseño deja lista la otra mitad: el token interno y `introspect`.
- **bcrypt o Argon2 para las contraseñas.** Son igual de buenos, pero piden una dependencia nueva; scrypt viene con Python.
- **`pyotp` para los códigos.** Sería una dependencia más para unas 30 líneas que el estándar define con exactitud y que se prueban con sus vectores oficiales.
- **Dibujar el QR en el navegador.** Habría que mandar el secreto en claro a una librería de JavaScript; es mejor generarlo en el servidor.
- **Guardar el secreto del código sin cifrar.** Lo protegería la seguridad por filas, pero un respaldo robado expondría todos los códigos.
- **JWT como token interno.** No se puede revocar al instante. La sesión en Redis con `introspect` sí.

## Consecuencias

- **Primer ingreso.** Cada persona escanea un QR la primera vez, igual que en Oráculo. Si cambia de celular, el superusuario le da «Reiniciar autenticador».
- **La pimienta del servidor.** Si se pierde o cambia `AUTH_KEY_PEPPER`, dejan de servir las llaves de sistema y todos los Authenticators. Las contraseñas no dependen de ella. Se recupera con `make acceso --reiniciar-codigo` para cada persona.
- **Redis.** Las sesiones viven ahí. Si Redis se reinicia sin su respaldo en disco, todos vuelven a entrar; no se pierde nada más.
- **Migración 0040.** Agrega a `users` las columnas de contraseña, código y bloqueo. Los usuarios que ya existían quedan sin contraseña: el superusuario les da una temporal desde «Accesos» o con `make acceso`.
- **HTTPS.** Mientras se sirva por `http://` en la red interna, `AUTH_COOKIE_SECURE=false`.
