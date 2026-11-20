/**
 * Dirección base de la API y armado de URLs.
 *
 * Lo usan los servicios de src/services/ (nunca los componentes, CLAUDE.md
 * §6.2) y el mapa, que arma las URLs de las teselas. La API siempre se pide
 * en el mismo sitio que la pantalla: en desarrollo la reenvía Vite y en
 * producción nginx, así el navegador nunca conoce el host real de la API ni
 * sus llaves.
 *
 * Detrás del gateway de Oráculo la pantalla vive en `/m/noticias/` y no en la
 * raíz (ADR-0119): por eso las rutas parten de la base de la página
 * (`import.meta.env.BASE_URL`, que el build deja en `./`) y nunca de `/`.
 */

/** Base de la página que pone Vite: `/` en desarrollo y pruebas, `./` en el build. */
const PAGE_BASE = import.meta.env.BASE_URL;

/** Prefijo de la versión 1 de la API REST (especificación, sección 13). */
export const API_BASE_PATH = `${PAGE_BASE}api/v1`;

/**
 * Arma la URL de un endpoint de la API, relativa a la página.
 *
 * @param path Ruta del endpoint, con o sin diagonal inicial (`health` o `/health`).
 * @returns La ruta completa: `/api/v1/health` en desarrollo y `./api/v1/health`
 *   en el build, que el navegador resuelve junto a la página (en la raíz o
 *   bajo `/m/noticias/`).
 * @throws {Error} Si la ruta está vacía.
 * @example apiUrl('health') // '/api/v1/health' en desarrollo
 */
export function apiUrl(path: string): string {
  const trimmed = path.trim().replace(/^\/+/, '');
  if (trimmed === '') {
    throw new Error('La ruta del endpoint no puede estar vacía.');
  }
  return `${API_BASE_PATH}/${trimmed}`;
}

/**
 * Dirección absoluta de la carpeta de la página, sin la diagonal final.
 *
 * El mapa la necesita porque PMTiles solo acepta URLs absolutas
 * (`pmtiles://http://...`). `window.location.origin` no sirve detrás del
 * gateway: perdería el `/m/noticias` y pediría las teselas a Oráculo.
 *
 * @param documentUrl Dirección del documento; por defecto, la de la página.
 * @param base Base de Vite; por defecto, la del build.
 * @returns Por ejemplo `https://oraculo/m/noticias` o `http://localhost:8080`.
 * @example pageBase('https://oraculo/m/noticias/', './') // 'https://oraculo/m/noticias'
 */
export function pageBase(documentUrl: string = document.baseURI, base: string = PAGE_BASE): string {
  return new URL(base, documentUrl).href.replace(/\/+$/, '');
}
