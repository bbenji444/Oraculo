# ADR-0125: El freno de intentos no bloquea a quien tiene una llave vigente

- **Estado:** propuesto (20/11/2026).
- **Fase:** F12.
- **Relacionadas:** ADR-0042 (llaves y freno de intentos), ADR-0119 (gateway), ADR-0124 (una sola llave por persona).

## Contexto

El 20/11/2026, Benji cambió de llave y al volver a entrar vio «Demasiados intentos fallidos desde este equipo. Espera unos minutos.». En Redis de la VM estaba el contador `monitor:fallos-llave:10.244.83.211`, con 10 fallos y unos 12 minutos por delante.

Esa IP es la de Oráculo. Detrás del gateway, todas las peticiones llegan con ella (`ORACULO_GATEWAY_IPS` no está puesta en la VM), así que el freno era uno solo para todos los usuarios.

Cada carga de la pantalla hace varias peticiones. Mientras Oráculo seguía mandando la llave vieja, ya revocada, cada una sumaba un fallo. En segundos se llegaba a 10 y el monitor quedaba cerrado 15 minutos **para todos**, incluso con llave buena: el freno se revisaba antes que la llave.

## Decisión

1. **Una llave vigente siempre entra**, aunque la IP esté frenada. El freno solo detiene llaves que no sirven.
2. **Una llave auténtica pero revocada o vencida no suma fallo.** La huella coincide, así que no es alguien adivinando: es alguien que cambió de llave. Sí queda en la bitácora como `auth.login_failed`.
3. **Las llaves falsas siguen sumando fallos.** Al décimo fallo en 15 minutos, esa IP recibe 429 con cualquier llave que no sirva.
4. **Una entrada buena ya no borra el contador.** Con la IP compartida, cualquier entrada correcta lo reiniciaba y dejaba intentar sin fin.

## Alternativas consideradas

- **Poner `ORACULO_GATEWAY_IPS`** para tomar la IP real del usuario desde `X-Forwarded-For`. Sirve solo si Oráculo manda ese encabezado, y eso no está confirmado. Queda como mejora aparte; no resuelve que una llave buena quede bloqueada.
- **Subir el tope de fallos.** Descartada: solo retrasa el bloqueo general.
- **Quitar el freno.** Descartada: sigue sirviendo contra quien prueba llaves inventadas.

## Consecuencias

- Quien tenga una llave vigente puede saber que es válida aunque la IP esté frenada. No importa en la práctica: el secreto es aleatorio de 40 caracteres y no se puede adivinar.
- Cambiar de llave ya no bloquea a nadie.
