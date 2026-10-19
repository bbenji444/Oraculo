/**
 * Descargas de la búsqueda abierta (§15, ADR-0018): reporte PDF, datos CSV y
 * GeoJSON, y la vista para imprimir.
 *
 * Los archivos los pide `services/reports.ts`; aquí se guardan con el nombre
 * que sugiere la API o se abren en otra pestaña. Una descarga a la vez: la
 * que corre se marca como "Generando…".
 *
 * "Imprimir" abre la pestaña en el mismo clic, antes de pedir el reporte: si
 * se abriera al terminar la petición, el navegador la bloquearía como ventana
 * emergente.
 */
import { useMutation } from '@tanstack/react-query';

import type { ApiFile } from '../services/http';
import { fetchExport, fetchReport } from '../services/reports';

export type DownloadKind = 'pdf' | 'csv' | 'geojson' | 'print';

// Tiempo antes de liberar el archivo en memoria: el navegador lo sigue
// leyendo un momento después del clic que inicia la descarga.
const REVOKE_DELAY_MS = 60_000;

const FALLBACK_NAME: Record<Exclude<DownloadKind, 'print'>, string> = {
  pdf: 'reporte.pdf',
  csv: 'notas.csv',
  geojson: 'notas.geojson',
};

/**
 * Guarda un archivo de la API en la computadora (descarga normal del navegador).
 *
 * @param file Contenido y nombre sugerido.
 * @param fallbackName Nombre si la API no sugirió uno.
 */
export function saveFile(file: ApiFile, fallbackName: string): void {
  const url = URL.createObjectURL(file.blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = file.filename ?? fallbackName;
  document.body.append(link);
  link.click();
  link.remove();
  window.setTimeout(() => {
    URL.revokeObjectURL(url);
  }, REVOKE_DELAY_MS);
}

async function run(searchId: string, kind: DownloadKind, tab: Window | null): Promise<void> {
  if (kind === 'print') {
    const file = await fetchReport(searchId, 'html');
    if (tab) {
      tab.location.href = URL.createObjectURL(file.blob);
    } else {
      // El navegador no dejó abrir otra pestaña: se descarga la página.
      saveFile(file, 'reporte.html');
    }
    return;
  }
  const file =
    kind === 'pdf' ? await fetchReport(searchId, 'pdf') : await fetchExport(searchId, kind);
  saveFile(file, FALLBACK_NAME[kind]);
}

/**
 * Descargas de una búsqueda.
 *
 * @param searchId Búsqueda abierta, o `null` si no hay.
 * @returns `start(kind)` para iniciar una descarga, cuál corre ahora y el
 *   último error (mensaje de la API en español).
 */
export function useDownloads(searchId: string | null) {
  const mutation = useMutation({
    mutationFn: ({ kind, tab }: { kind: DownloadKind; tab: Window | null }) =>
      run(searchId ?? '', kind, tab),
    onError: (_error, { tab }) => {
      tab?.close();
    },
  });
  return {
    start(kind: DownloadKind) {
      if (!searchId || mutation.isPending) return;
      const tab = kind === 'print' ? window.open('', '_blank') : null;
      // Mientras llega el reporte, la pestaña nueva dice qué está pasando.
      if (tab) {
        tab.document.title = 'Generando el reporte…';
        tab.document.body.textContent = 'Generando el reporte…';
        tab.document.body.style.cssText = 'font: 15px sans-serif; color: #475569; margin: 40px';
      }
      mutation.mutate({ kind, tab });
    },
    running: mutation.isPending ? mutation.variables.kind : null,
    error: mutation.error,
  };
}
