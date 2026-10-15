/**
 * Dirección base de la API y armado de URLs.
 *
 * Lo usan los servicios de src/services/ (nunca los componentes, CLAUDE.md
 * §6.2). La API siempre se pide por ruta relativa (/api/v1/...): en
 * desarrollo la reenvía Vite y en producción nginx, así el navegador nunca
 * conoce el host real de la API ni sus llaves.
 */

/** Prefijo de la versión 1 de la API REST (especificación, sección 13). */
export const API_BASE_PATH = '/api/v1';

/**
 * Arma la URL relativa de un endpoint de la API.
 *
 * @param path Ruta del endpoint, con o sin diagonal inicial (`health` o `/health`).
 * @returns La ruta completa, por ejemplo `/api/v1/health`.
 * @throws {Error} Si la ruta está vacía.
 * @example apiUrl('health') // '/api/v1/health'
 */
export function apiUrl(path: string): string {
  const trimmed = path.trim().replace(/^\/+/, '');
  if (trimmed === '') {
    throw new Error('La ruta del endpoint no puede estar vacía.');
  }
  return `${API_BASE_PATH}/${trimmed}`;
}
