# ADR-0120: La llave de API se ve una sola vez

- **Estado:** propuesto (20/11/2026).
- **Fase:** F12.
- **Reemplaza en parte:** ADR-0047 (la copia cifrada y los botones «Ver» y «Copiar»).
- **Relacionadas:** ADR-0042 (llaves de sistema, que ya se veían una sola vez), ADR-0119 (gateway de Oráculo).

## Contexto

Desde el ADR-0047 cada persona tenía una «Llave de API» en «Accesos». El monitor guardaba dos cosas de ella:

- la huella HMAC (`key_hash`), con la que se comprueba cada petición;
- la llave completa cifrada (`access_keys.secret_sealed`, AES-256-GCM), para que un superusuario la volviera a ver o copiar cuando quisiera.

Con el gateway (ADR-0119) esa llave es la que Oráculo guarda y manda en cada petición de la persona. Benji, el 20/11/2026: «necesito que me permitas ver una sola vez la api key y después no se pueda ver de nuevo bajo ningún motivo, solo generar una nueva».

Mientras exista la copia cifrada, la llave **sí** se puede volver a ver: con la pantalla, con la API o con un respaldo de la base junto con `AUTH_KEY_PEPPER`. Ocultar el botón no basta.

## Decisión

1. **No se guarda la llave.** La migración 0051 borra `access_keys.secret_sealed`. Del lado del monitor solo queda la huella, que no se puede revertir.
2. **Se ve una sola vez**, en la respuesta de `POST /access/users/{id}/api-key` (`Cache-Control: no-store`). La pantalla la enseña en el mismo aviso que las llaves de sistema: «Cópiala ahora: no se vuelve a mostrar». Al cerrarlo desaparece.
3. **Se quita `GET /access/users/{id}/api-key`** (ahora responde 405). Con él se van los botones «Ver» y «Copiar» y la acción de bitácora `access_key.revealed`; las entradas viejas se siguen leyendo.
4. **Si se pierde, «Generar nueva».** Revoca la anterior al instante y cierra sus sesiones, igual que antes.
5. **La persona nace sin llave.** Antes se generaba sola al crearla. Como ahora solo se ve una vez, la genera el superusuario cuando la va a copiar; si no, se perdería sin que nadie la viera.
6. **Columna `is_api_key`** para seguir distinguiendo la llave de API de las llaves de sistema. Antes lo decía `secret_sealed IS NOT NULL`. Lleva un índice parcial para la llave vigente de cada persona.

## Alternativas consideradas

- **Dejar la copia cifrada y solo quitar el botón.**
  - Pros: no hay migración.
  - Contras: la llave sigue siendo legible para quien tenga la base y la pimienta, y un cambio futuro podría volver a mostrarla. No cumple «bajo ningún motivo».
- **Mostrarla una vez y borrar la copia al cerrar el aviso.**
  - Contras: si el navegador se cierra antes, la copia se queda guardada, y hace falta otra ruta para avisar «ya la vi».
  - Se descartó: no guardarla nunca es más simple y más seguro.

## Consecuencias

- **Llave propia (20/11/2026).** Si quien genera la llave es la misma persona que usa la pantalla, su llave anterior deja de servir en ese instante y la API responde 401. La salida por sesión terminada se detiene (`holdSession`) mientras el aviso está abierto; al cerrarlo, la página se recarga y la persona entra con la llave nueva desde Oráculo.

- **Las llaves que ya existen siguen sirviendo**, incluidas las que ya estén pegadas en Oráculo. Lo único que se pierde es poder volver a verlas; quien no la tenga copiada usa «Generar nueva».
- **Bajar la migración** recrea `secret_sealed` vacía y quita `is_api_key`. Las llaves de API pasan a contarse como llaves de sistema y siguen sirviendo. Las copias borradas no se recuperan.
- **Personas nuevas:** después de «Nueva persona» hay que «Generar llave» para Oráculo.
- **`AUTH_KEY_PEPPER` sigue cifrando el secreto de Authenticator**, pero ya no protege ninguna llave de API.
