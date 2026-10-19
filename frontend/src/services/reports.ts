/**
 * Servicio de reportes y datos de una búsqueda (§13 y §15, ADR-0018).
 *
 * - `POST /searches/{id}/report?format=pdf|html`: el reporte. La primera vez
 *   el backend le pide el resumen ejecutivo a la IA (~0.001 USD).
 * - `GET /searches/{id}/export?format=csv|geojson`: las notas como datos.
 *
 * Solo pide los archivos; guardarlos o abrirlos es cosa de `useDownloads`.
 */
import { apiUrl } from '../config/api';
import { type ApiFile, requestFile } from './http';

export type ReportFormat = 'pdf' | 'html';
export type ExportFormat = 'csv' | 'geojson';

function searchPath(searchId: string, action: string, format: string): string {
  return `${apiUrl(`searches/${encodeURIComponent(searchId)}/${action}`)}?format=${format}`;
}

/**
 * El reporte de una búsqueda terminada.
 *
 * @throws {ApiError} `search_not_finished` (409) si todavía corre.
 */
export function fetchReport(searchId: string, format: ReportFormat): Promise<ApiFile> {
  return requestFile(searchPath(searchId, 'report', format), 'POST');
}

/**
 * Las notas relevantes de una búsqueda terminada, en CSV o GeoJSON.
 *
 * @throws {ApiError} `search_not_finished` (409) si todavía corre.
 */
export function fetchExport(searchId: string, format: ExportFormat): Promise<ApiFile> {
  return requestFile(searchPath(searchId, 'export', format));
}
