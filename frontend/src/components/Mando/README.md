# Centro de mando (diseño 3)

El diseño alterno de Explorar: la búsqueda como una consola de misión abajo, el globo encima y los resultados en un expediente a la derecha (ADR-0037). Se enciende con `?mando` en la URL:

```
http://localhost:8080/?mando#/explorar
```

Sin `?mando` se ve el diseño 2 («consola táctica», ADR-0036), que no cambia.

| Archivo               | Qué hace                                                                                                                        |
| --------------------- | ------------------------------------------------------------------------------------------------------------------------------- |
| `MandoPanels.tsx`     | Acomoda las piezas sobre el globo y mide el alto de la consola.                                                                 |
| `MissionDock.tsx`     | La consola: la frase de la misión con sus tarjetas, el costo, «Iniciar barrido», las misiones recientes, el reloj y los atajos. |
| `MissionProgress.tsx` | Mientras se busca: el riel de etapas, el porcentaje, el cronómetro y la bitácora.                                               |
| `ScanOverlay.tsx`     | El radar sobre el globo y el letrero «BARRIDO COMPLETO».                                                                        |
| `Dossier.tsx`         | El expediente: las cifras, las categorías, la cronología o la lista, y las descargas.                                           |
| `mission.ts`          | La lógica pura: los textos de la frase, el horario de las corridas automáticas, las misiones recientes y la bitácora.           |

## Dónde viven las demás piezas

- **Estilos:** `src/styles/mando.css`.
- **Estado propio:** `src/store/mando.ts`. Guarda qué tarjeta está abierta, si se ve el expediente y el alto de la consola.
- **Lo que comparte con el diseño 2:**
  - la búsqueda misma, en `store/explorer.ts`;
  - `useSearchLauncher`;
  - los controles de cada parte de la frase;
  - la cronología y la lista.
