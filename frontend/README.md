# frontend/

Interfaz web del monitor de noticias: React 18 + TypeScript + Vite, con Tailwind CSS para estilos.
Corre **solo en Windows** con Node 22; no instales sus dependencias desde Ubuntu (ver [ADR-0006](../docs/adr/0006-entorno-desarrollo-sin-docker.md)): las librerías de Node traen binarios distintos para cada sistema.

## Estructura

| Carpeta           | Qué hay                                                                                       |
| ----------------- | --------------------------------------------------------------------------------------------- |
| `src/config/`     | Constantes de configuración (por ejemplo, la ruta base de la API).                            |
| `src/services/`   | Llamadas HTTP a la API. Los componentes nunca llaman a `fetch` directamente (CLAUDE.md §6.2). |
| `src/components/` | Componentes de React, pequeños y con una sola responsabilidad.                                |
| `src/styles/`     | Estilos globales y configuración de Tailwind.                                                 |
| `public/`         | Archivos estáticos que se sirven tal cual (ícono).                                            |

Más adelante: `src/stores/` (estado global con Zustand) y `src/hooks/`.

## Comandos (PowerShell, dentro de `frontend/`)

```powershell
npm install        # una vez, o cuando cambie package.json
npm run dev        # servidor de desarrollo en http://localhost:5173 (reenvía /api a la API en WSL)
npm run test       # pruebas con Vitest
npm run lint       # ESLint + Prettier
npm run format     # aplica el formato de Prettier
npm run build      # build de producción en dist/ (lo sirve nginx)
```

Las versiones están fijadas exactamente en `package.json` y `package-lock.json`.
TypeScript está en la serie 6 porque typescript-eslint todavía no soporta la 7.
