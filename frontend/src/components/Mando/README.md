# Centro de mando (diseño 3)

El diseño principal de Explorar desde el 27/10/2026 (ADR-0037): la búsqueda como una consola de consulta de vidrio abajo, el globo encima y los resultados en un expediente a la derecha.

El diseño anterior, con la columna a la izquierda (ADR-0036), se ve con `?clasico` en la URL:

```
http://localhost:8080/?clasico#/explorar
```

| Archivo               | Qué hace                                                                                                                |
| --------------------- | ----------------------------------------------------------------------------------------------------------------------- |
| `MandoPanels.tsx`     | Acomoda las piezas sobre el globo y mide el alto de la consola.                                                         |
| `MissionDock.tsx`     | La consola en tres zonas: radar, la frase con sus tarjetas y las consultas recientes, y el costo con «Iniciar barrido». |
| `MissionProgress.tsx` | Mientras se busca: el riel de etapas, el porcentaje, el cronómetro y la bitácora.                                       |
| `ScanOverlay.tsx`     | El radar sobre el globo y el letrero «BARRIDO COMPLETO».                                                                |
| `Dossier.tsx`         | El expediente: las cifras, las categorías, la cronología o la lista, y las descargas.                                   |
| `mission.ts`          | La lógica pura: los textos de la frase, el horario de las corridas automáticas, las consultas recientes y la bitácora.  |

## Dónde viven las demás piezas

- **Estilos:** `src/styles/mando.css`.
- **Estado propio:** `src/store/mando.ts`. Guarda qué tarjeta está abierta, si se ve el expediente y el alto de la consola.
- **Lo que comparte con el diseño 2:**
  - la búsqueda misma, en `store/explorer.ts`;
  - `useSearchLauncher`;
  - los controles de cada parte de la frase;
  - la cronología y la lista.
