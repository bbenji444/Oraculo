# ADR-0047: Código de 6 dígitos opcional y llave de API visible por usuario

- **Estado:** aceptada
- **Fecha:** 2026-11-11
- **Fase:** F12
- **Relacionadas:** ADR-0042 (llaves y seguridad por filas), ADR-0043 (contraseña, código y token interno)

## Contexto

Benji, 11/11/2026:

- «Vamos a quitar lo de la autenticación con código, dice mi jefe que es tedioso.»
- Quiere un interruptor: «que tú desde el panel puedas encenderlo o apagarlo».
- «Cada usuario debe tener su propia API key, la cual se debe de ver en el usuario para poder interconectarlo con el resto del sistema.» El otro desarrollador la conecta con el resto del código.

Lo que decidió:

- solo los superusuarios ven las llaves; los usuarios normales no ven nada de esto;
- se muestran directo, sin volver a pedir la contraseña.

Hasta ahora (ADR-0042) la llave completa salía **una sola vez**. En la base solo quedaba su huella HMAC, así que nadie la podía volver a ver.

## Decisión

1. **Interruptor del código** (`auth_settings.totp_required`, migración 0044):
   - una sola fila;
   - el superusuario lo cambia en «Accesos» (`PUT /access/settings`) y queda en la bitácora (`auth.totp_setting`);
   - arranca **apagado**: se entra con usuario y contraseña.
2. **Con el código apagado**, `POST /auth/login` (o el cambio de contraseña temporal) abre la sesión de inmediato:
   - responde `next: "done"` con la persona en `me`;
   - deja el token interno en la cookie `monitor_sesion`, igual que antes;
   - los pasos del QR y del código ya no aplican.
3. **Con el código prendido** todo vuelve a ser como en ADR-0043. Los secretos de Authenticator que ya existían nunca se borraron: quien ya lo conectó usa el mismo, y quien no, lo conecta al entrar.
4. **Llave de API por persona**:
   - la etiqueta es «Llave de API», sin vencimiento;
   - se guarda dos veces: la huella HMAC (`key_hash`), con la que se sigue comprobando cada petición, y la llave completa **cifrada** (`access_keys.secret_sealed`, AES-256-GCM con una llave derivada de `AUTH_KEY_PEPPER`, la misma caja que el secreto de Authenticator).
5. **Cada persona nueva nace con su llave.** A las que ya existían se les genera con «Generar llave».
6. **Solo superusuarios:**
   - `GET /access/users/{id}/api-key` muestra la llave completa. Cada vista queda en la bitácora (`access_key.revealed`) y la respuesta lleva `Cache-Control: no-store`.
   - `POST /access/users/{id}/api-key` genera otra. La anterior se revoca al instante y se cierran las sesiones abiertas con ella: una sola llave de API por persona.
7. **Pantalla «Accesos»:** el interruptor arriba y, en cada persona, su llave enmascarada con «Ver», «Copiar» y «Generar nueva» (esta pide confirmar). La etiqueta «Sin Authenticator» solo aparece con el código prendido.
8. **Uso desde otro sistema:** `Authorization: Bearer orc_live_…` actúa **como esa persona**, con su rol y su seguridad por filas. Guía para el otro desarrollador: `docs/guia-integracion-api.md`.

Las «llaves de sistema» de ADR-0042 (varias por persona, con vencimiento, se ven una sola vez) siguen igual.

## Alternativas consideradas

- **Borrar el código por completo.** Benji prefirió un interruptor: volver a pedirlo es un clic.
- **Llaves que solo se ven al crearlas** (como ADR-0042). Es más seguro, pero no cumple «que se vea en el usuario y lo puedas copiar».
- **Pedir la contraseña antes de mostrar una llave.** Benji lo descartó por práctico.

## Consecuencias

- **Menos seguridad al entrar:** sin código, una contraseña robada basta. Lo atenúan:
  - el bloqueo tras 5 fallos y el freno por IP;
  - la regla de contraseñas de 12+ caracteres;
  - el interruptor, que en cualquier momento vuelve a pedir el código.
- **Riesgo de las llaves cifradas:** quien tenga a la vez una copia de la base **y** `AUTH_KEY_PEPPER` (solo en el `.env` del servidor) puede leer todas las llaves de API. La pimienta no va en los respaldos de la base, así que no deben guardarse juntos.
- **Sesión abierta de un superusuario:** quien llegue a una sesión de superusuario abierta puede copiar todas las llaves, porque no se pide contraseña. Queda registrado en la bitácora quién vio cada una.
- **Integración:** el otro desarrollador debe guardar cada llave como secreto (variable de entorno o bóveda) y nunca en el código ni en el navegador.
- **Llave filtrada:** si una llave se filtra, «Generar nueva» la invalida al instante.
