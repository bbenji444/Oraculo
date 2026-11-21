# ADR-0124: Una sola llave vigente por persona

- **Estado:** propuesto (20/11/2026).
- **Fase:** F12.
- **Relacionadas:** ADR-0042 (llaves de sistema), ADR-0047 (llave de API), ADR-0120 (la llave se ve una vez), ADR-0121 (sin entrada con contraseña).

## Contexto

Benji, el 20/11/2026: cambió su llave en Oráculo por la nueva y el monitor lo dejaba entrar **con las dos**, la vieja y la nueva.

Causa, revisada en la VM con `make crear-llave ARGS="--listar"`: su usuario tenía dos llaves vigentes de tipos distintos.

- Una **de consola** (`make crear-llave`, «Creada en la consola»): es una llave de sistema.
- Una **de API**, la que se genera en «Accesos».

«Generar nueva» solo revocaba la llave de API anterior. `make crear-llave` y «+ Nueva llave» no revocaban nada, porque las llaves de sistema podían convivir (hasta 5). Como sin contraseña toda llave vigente sirve para entrar por Oráculo, cualquier llave «olvidada» seguía abriendo el monitor.

Además, al generar su propia llave la pantalla lo sacaba antes de copiarla, y luego quedaba abierta sin límite. Benji pidió que se cierre sola en «unos 10 segundos».

## Decisión

1. **Cada persona tiene una sola llave vigente.** Crear una llave para alguien, por cualquier camino («Generar nueva», «+ Nueva llave» o `make crear-llave`), revoca **todas** sus llaves anteriores y cierra las sesiones que entraron con ellas. Se quita el tope de 5 llaves, que ya no tiene sentido.
2. **La llave propia se cierra sola.** Si quien la genera es la misma persona que usa la pantalla:
   - el aviso con la llave se queda abierto aunque la anterior ya no sirva;
   - muestra una cuenta regresiva de 10 segundos (`OWN_KEY_CLOSE_SECONDS`);
   - al terminar la cuenta, o al cerrarlo, la página se recarga;
   - la persona vuelve a entrar desde Oráculo con la llave nueva (`frontend/src/components/Access/ownKey.ts`).

## Alternativas consideradas

- **Revocar solo las del mismo tipo** (como antes). Descartada: es justo lo que dejó entrar con dos llaves.
- **Dejar varias llaves y avisar.** Descartada: Benji pidió que solo sirva la nueva, y cada llave extra es una puerta más.
- **Cerrar el aviso al instante.** Descartada: no da tiempo de copiar la llave y la persona se queda sin acceso (pasó el 20/11/2026).

## Consecuencias

- Si alguien usaba una llave de sistema para otro programa, al generarle una llave nueva ese programa deja de entrar; hay que darle la nueva.
- Las llaves que ya estaban vigentes antes de este cambio siguen vigentes hasta que se genere una nueva. Para dejar una sola: «Generar nueva» una vez en el renglón de la persona.
- `docs/api.md` ya no lista la regla de «máximo 5 llaves vigentes».
