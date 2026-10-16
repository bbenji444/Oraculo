# frontend/

Interfaz web del monitor de noticias: React 18 + TypeScript + Vite, con Tailwind CSS para estilos.
Corre **solo en Windows** con Node 22; no instales sus dependencias desde Ubuntu (ver [ADR-0006](../docs/adr/0006-entorno-desarrollo-sin-docker.md)): las librerías de Node traen binarios distintos para cada sistema.

## Estructura

| Carpeta           | Qué hay                                                                                                                            |
| ----------------- | ---------------------------------------------------------------------------------------------------------------------------------- |
| `src/config/`     | Constantes de configuración (por ejemplo, la ruta base de la API).                                                                 |
| `src/map/`        | Estilo del globo (MapLibre v6 + Protomaps + capas INEGI) y configuración del worker y PMTiles.                                     |
| `src/services/`   | Llamadas HTTP a la API (`http.ts` es el cliente compartido). Los componentes nunca llaman a `fetch` directamente (CLAUDE.md §6.2). |
| `src/components/` | Componentes de React, pequeños y con una sola responsabilidad.                                                                     |
| `src/styles/`     | Estilos globales y configuración de Tailwind.                                                                                      |
| `public/`         | Archivos estáticos que se sirven tal cual (ícono).                                                                                 |

Además, `src/hooks/` tiene los hooks que conectan los servicios con TanStack Query (por ejemplo, `useHealth`). Más adelante se agrega `src/stores/` (estado global con Zustand).

## Pantallas

- **Geodatos** (`#/geodatos`, inicial): globo 3D con el catálogo de regiones de INEGI. Busca una región o haz clic en el mapa; la tarjeta muestra migas de pan navegables, clave INEGI y punto, y el mapa vuela a ella. Base del globo de la Fase 6.
- **Conceptos** (`#/conceptos`): tabla de conceptos con interruptor de activo, formulario para crear o editar (palabras clave y exclusiones como "chips", color) con los errores del backend junto a cada campo, y **Probar concepto**: eliges región y rango y ves las consultas exactas por proveedor, sin gastar créditos (historia H2).
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
