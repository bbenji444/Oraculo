/**
 * Controles sobre el globo: «Mis casos», día/noche y la leyenda de precisión
 * (Benji, 11/11/2026: el giro es automático y la animación siempre lenta, ya
 * no se eligen) (§14.2: lo ubicado solo por estado o país se dibuja con
 * anillo punteado, para no hacer creer que pasó en el centro exacto).
 * También los botones de Descargas: reporte PDF, datos CSV y GeoJSON, e imprimir
 * (Fase 7, ADR-0018), que van dentro del renglón de la búsqueda terminada, y el
 * aviso de "Búsqueda lista".
 */
import { type DownloadKind, useDownloads } from '../../hooks/useDownloads';
import { useExplorerStore } from '../../store/explorer';
import { EarthToggle } from '../GeoExplorer/EarthToggle';
import type { FinishNotice } from './format';
import { SMALL_BUTTON } from './ui';

/**
 * Interruptor «Mis casos» (9.6, D9): mis casos abiertos como marcadores ámbar
 * en el globo. Lo usan los dos diseños de Explorar.
 */
export function MyCasesToggle() {
  const showCases = useExplorerStore((s) => s.showCases);
  return (
    <button
      type="button"
      aria-pressed={showCases}
      onClick={() => {
        useExplorerStore.getState().setShowCases(!showCases);
      }}
      title="Ver mis casos abiertos sobre el globo; clic en uno abre su muro"
      className={`hud-btn hud-btn--sm bg-[#050d12]/90 ${
        showCases ? 'border-amber-300/60 text-amber-200' : ''
      }`}
    >
      {showCases ? '● Mis casos' : '○ Mis casos'}
    </button>
  );
}

export function GlobeControls() {
  const earth = useExplorerStore((s) => s.earth);
  const setEarth = useExplorerStore((s) => s.setEarth);
  return (
    <div className="flex flex-wrap items-center gap-2">
      <EarthToggle earth={earth} onChange={setEarth} />
    </div>
  );
}

export function PrecisionLegend() {
  return (
    <div className="rounded-xl border border-sky-400/20 bg-[#050d12]/90 px-3 py-2 text-[11px] text-slate-300 shadow-lg shadow-black/40">
      <p className="flex items-center gap-2">
        <span aria-hidden="true" className="hud-dot hud-dot--live size-2.5" />
        Lugar preciso (municipio o localidad)
      </p>
      <p className="mt-1 flex items-center gap-2">
        <span
          aria-hidden="true"
          className="size-3 rounded-full border-2 border-dashed border-slate-200"
        />
        Solo estado o país: centro aproximado
      </p>
    </div>
  );
}

const DOWNLOADS: { kind: DownloadKind; short: string; label: string; hint: string }[] = [
  {
    kind: 'pdf',
    short: 'PDF',
    label: 'Reporte (PDF)',
    hint: 'Reporte de las notas relevantes: portada, resumen, mapa, gráficas y noticias. El primero de cada búsqueda cuesta ~0.0003 USD de IA; los siguientes, nada.',
  },
  {
    kind: 'csv',
    short: 'CSV',
    label: 'Datos (CSV)',
    hint: 'Una fila por nota relevante, para Excel',
  },
  {
    kind: 'geojson',
    short: 'GeoJSON',
    label: 'Puntos (GeoJSON)',
    hint: 'Las notas relevantes como puntos, para QGIS o Google Earth',
  },
  { kind: 'print', short: 'Imprimir', label: 'Imprimir', hint: 'Abre el reporte en otra pestaña' },
];
// Por ahora solo el PDF, que se va a corregir (Benji, 26/10/2026). CSV, GeoJSON
// e imprimir siguen funcionando en la API y en `useDownloads`: para volver a
// mostrarlos basta agregarlos aquí.
const VISIBLE_DOWNLOADS: readonly DownloadKind[] = ['pdf'];
// Con un solo botón, el texto completo cabe y se entiende mejor que «PDF».
const SINGLE_DOWNLOAD_TEXT = 'Descargar reporte (PDF)';

/**
 * Descargas de una búsqueda terminada (§15, ADR-0018), en una fila de botones
 * cortos dentro del renglón de la búsqueda: así no le quitan espacio a la lista
 * de noticias. Mientras se genera un archivo, su botón dice "Generando…"; el
 * nombre completo y lo que cuesta van en la ayuda del botón.
 *
 * @param props.searchId Búsqueda terminada.
 */
export function DownloadButtons({
  searchId,
  compact = false,
}: {
  searchId: string;
  /** Solo «PDF» en el botón (el resumen del expediente, donde el espacio cuenta). */
  compact?: boolean;
}) {
  const downloads = useDownloads(searchId);
  const visible = DOWNLOADS.filter((d) => VISIBLE_DOWNLOADS.includes(d.kind));
  const single = visible.length === 1 && !compact;
  return (
    <div aria-label="Descargas" role="group" className="space-y-1">
      <div
        className="grid gap-1"
        style={{ gridTemplateColumns: `repeat(${String(visible.length)}, minmax(0, 1fr))` }}
      >
        {visible.map(({ kind, short, label, hint }) => (
          <button
            key={kind}
            type="button"
            aria-label={label}
            disabled={downloads.running !== null}
            title={hint}
            onClick={() => {
              downloads.start(kind);
            }}
            className={`${SMALL_BUTTON} flex items-center justify-center gap-1 px-1 py-0.5 text-[11px] ${
              kind === 'pdf' ? 'border-sky-400/40 bg-sky-500/15 text-sky-100' : ''
            }`}
          >
            {downloads.running === kind ? (
              <span
                aria-hidden="true"
                className="size-3 animate-spin rounded-full border-2 border-slate-500 border-t-sky-300"
              />
            ) : single ? (
              SINGLE_DOWNLOAD_TEXT
            ) : (
              short
            )}
          </button>
        ))}
      </div>
      {downloads.running && (
        <p aria-live="polite" className="text-[11px] text-slate-400">
          Generando…
        </p>
      )}
      {downloads.error && (
        <p role="alert" className="text-[11px] text-rose-300">
          {downloads.error.message}
        </p>
      )}
    </div>
  );
}

const NOTICE_TONE: Record<FinishNotice['tone'], string> = {
  ok: 'text-emerald-300',
  warn: 'text-amber-300',
  error: 'text-rose-300',
};

/**
 * Aviso flotante de "Búsqueda lista" (ver `useFinishNotice`), abajo al centro
 * para no tapar el panel ni los controles del globo.
 *
 * @param props.notice Aviso a mostrar, o `null` para no mostrar nada.
 * @param props.onClose Cierra el aviso antes de que se quite solo.
 */
export function FinishToast({
  notice,
  onClose,
}: {
  notice: FinishNotice | null;
  onClose: () => void;
}) {
  return (
    <div
      role="status"
      aria-live="polite"
      className="pointer-events-none absolute inset-x-0 bottom-6 z-30 flex justify-center px-4"
    >
      {notice && (
        <div className="hud-panel hud-reveal pointer-events-auto flex items-center gap-3 px-4 py-2.5 text-sm text-slate-100">
          <span aria-hidden="true" className={NOTICE_TONE[notice.tone]}>
            {notice.tone === 'ok' ? '✓' : notice.tone === 'warn' ? '⚠' : '✕'}
          </span>
          {notice.text}
          <button
            type="button"
            onClick={onClose}
            aria-label="Cerrar aviso"
            className="hud-icon-btn size-7"
          >
            ×
          </button>
        </div>
      )}
    </div>
  );
}
