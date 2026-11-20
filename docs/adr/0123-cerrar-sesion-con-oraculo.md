# ADR-0123: Al salir de Oráculo, el monitor se cierra

- **Estado:** propuesto (20/11/2026).
- **Fase:** F12.
- **Relacionadas:** ADR-0119 (gateway), ADR-0121 (sin entrada con contraseña).

## Contexto

El jefe de Benji, el 20/11/2026: al cerrar sesión, la sesión tiene que morir; parecía quedarse abierta «por las cookies o el caché».

Con el gateway, el monitor no tiene sesión propia: Oráculo manda la llave en cada petición. Al salir de Oráculo, su middleware ya no reenvía nada y responde con su pantalla de entrada. Aun así quedaban tres huecos:

1. **Cookie de antes.** Una cookie `monitor_sesion` de cuando se entraba con contraseña seguía valiendo hasta caducar (hasta 12 h). Con ella se podía entrar por la IP de la VM.
2. **Pestaña abierta.** Si se sale de Oráculo en otra pestaña, la del monitor seguía mostrando lo que ya tenía cargado. La siguiente petición recibía la pantalla de entrada de Oráculo (HTML tras un 302), no un 401, y la pantalla no lo reconocía.
3. **Botón «atrás».** `index.html` iba con `no-cache` y el navegador podía mostrar la página de memoria.

## Decisión

1. **Sin `PASSWORD_LOGIN` la cookie no vale.** Solo entra la llave Bearer. Una cookie vieja recibe 401 y la orden de borrarse.
2. **La pantalla detecta la salida de Oráculo.** Si la respuesta llegó por una redirección y trae HTML en lugar de la API, se olvida a la persona y se recarga la página. Así Oráculo muestra su pantalla de entrada.
3. **Al volver a la pestaña** se pregunta otra vez quién es (`/auth/me`).
4. **`index.html` con `no-store`**: el navegador no la guarda, tampoco para «atrás». La API ya respondía `no-store`.

## Alternativas consideradas

- **Que Oráculo avise al monitor al cerrar sesión** (webhook o lista de revocación).
  - Contras: hay que construirlo en el core, y no hace falta porque el monitor no guarda sesión.
- **Consultar `/auth/me` cada pocos segundos.**
  - Contras: tráfico constante. Basta con revisar en cada petición y al volver a la pestaña.

## Consecuencias

- **Salir de Oráculo cierra el monitor** en la siguiente petición o al volver a la pestaña.
- **Quien conserve una llave** sigue pudiendo usar la API con ella: se corta con «Generar nueva» (ADR-0120).
- **Con `PASSWORD_LOGIN=true`** las cookies vuelven a servir como antes.
