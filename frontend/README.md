# frontend/

Interfaz web del monitor de noticias: React 18 + TypeScript + Vite, con Tailwind CSS para estilos.
Corre **solo en Windows** con Node 22; no instales sus dependencias desde Ubuntu (ver [ADR-0006](../docs/adr/0006-entorno-desarrollo-sin-docker.md)): las librerías de Node traen binarios distintos para cada sistema.

## Estructura

| Carpeta           | Qué hay                                                                                                                                                    |
| ----------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `src/config/`     | Constantes de configuración (por ejemplo, la ruta base de la API).                                                                                         |
| `src/map/`        | Estilo del globo (MapLibre v6 + texturas de la NASA + Protomaps + capas INEGI), capas de noticias, fondo espacial y movimiento de la cámara (`motion.ts`). |
| `src/services/`   | Llamadas HTTP a la API (`http.ts` es el cliente compartido). Los componentes nunca llaman a `fetch` directamente (CLAUDE.md §6.2).                         |
| `src/hooks/`      | Hooks que conectan los servicios con TanStack Query (búsquedas, regiones, conceptos, estado).                                                              |
| `src/store/`      | Estado global con Zustand: lo que se ve en Explorar (región, conceptos, fechas, búsqueda y nota elegidas) y la cámara.                                     |
| `src/components/` | Componentes de React, pequeños y con una sola responsabilidad.                                                                                             |
| `src/styles/`     | Estilos globales, animaciones y configuración de Tailwind.                                                                                                 |
| `public/`         | Archivos estáticos que se sirven tal cual (ícono).                                                                                                         |

## Pantallas

- **Explorar** (`#/explorar`, inicial; `#/geodatos` también lleva aquí): el globo con la Tierra de la NASA sobre la Vía Láctea. A la izquierda, la búsqueda (región, conceptos, fechas, estimación de costo y avance), la lista de noticias y Descargas (activas en la Fase 7). A la derecha, "Top 5 estados" y "Tipos de noticias". Un clic en un punto vuela a la nota y abre su ficha (historia H1, ADR-0017).
- **Conceptos** (`#/conceptos`): tabla de conceptos con interruptor de activo, formulario para crear o editar (palabras clave y exclusiones como "chips", color) con los errores del backend junto a cada campo, y **Probar concepto**: eliges región y rango y ves las consultas exactas por proveedor, sin gastar créditos (historia H2).
- **Historial** (`#/historial`): búsquedas anteriores con su estado, notas y costo; "Abrir en el globo" las vuelve a mostrar en Explorar sin gastar nada.
- **Estado del sistema** (`#/estado`): semáforo de `/health`.

El mapa no usa servidores externos: teselas, fuentes y sprite los sirve nginx desde `geodata/output/` (ADR-0004, ADR-0007).

## Comandos (PowerShell, dentro de `frontend/`)

```powershell
npm install        # una vez, o cuando cambie package.json
npm run dev        # desarrollo en http://localhost:5173 (reenvía /api a la API y /tiles a nginx)
npm run test       # pruebas con Vitest
npm run lint       # ESLint + Prettier
npm run format     # aplica el formato de Prettier
npm run build      # build de producción en dist/ (lo sirve nginx)
```

Las versiones están fijadas exactamente en `package.json` y `package-lock.json`.
TypeScript está en la serie 6 porque typescript-eslint todavía no soporta la 7.
