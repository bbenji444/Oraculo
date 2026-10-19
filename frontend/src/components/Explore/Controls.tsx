/**
 * Controles sobre el globo: giro, día/noche, velocidad de las animaciones y
 * leyenda de precisión (§14.2: lo ubicado solo por estado o país se dibuja con
 * anillo punteado, para no hacer creer que pasó en el centro exacto).
 * También el panel de Descargas: reporte PDF, datos CSV y GeoJSON, e imprimir
 * (Fase 7, ADR-0018).
 */
import { type DownloadKind, useDownloads } from '../../hooks/useDownloads';
import { useSearch } from '../../hooks/useSearches';
import { MOTION_LABELS, MOTION_PRESETS } from '../../map/motion';
import { isFinished } from '../../services/searches';
import { useExplorerStore } from '../../store/explorer';
import { EarthToggle } from '../GeoExplorer/EarthToggle';
import { SpinToggle } from '../GeoExplorer/SpinToggle';
import { GLASS, PANEL_TITLE, SMALL_BUTTON } from './ui';

export function GlobeControls() {
  const spinning = useExplorerStore((s) => s.spinning);
  const setSpinning = useExplorerStore((s) => s.setSpinning);
  const earth = useExplorerStore((s) => s.earth);
  const setEarth = useExplorerStore((s) => s.setEarth);
  const motion = useExplorerStore((s) => s.motion);
  const setMotion = useExplorerStore((s) => s.setMotion);
  return (
    <div className="flex flex-wrap items-center gap-2">
      <SpinToggle
        spinning={spinning}
        onToggle={() => {
          setSpinning(!spinning);
        }}
      />
      <EarthToggle earth={earth} onChange={setEarth} />
      <label className="flex items-center gap-2 rounded-xl border border-slate-700/80 bg-slate-900/85 px-3 py-1.5 text-xs text-slate-300 shadow-lg shadow-black/30 backdrop-blur">
        Animación
        <select
          value={motion}
          onChange={(event) => {
            setMotion(event.target.value as (typeof MOTION_PRESETS)[number]);
          }}
          className="rounded-md bg-slate-800 px-1.5 py-0.5 text-xs text-slate-100 focus-visible:outline-2 focus-visible:outline-sky-400"
        >
          {MOTION_PRESETS.map((preset) => (
            <option key={preset} value={preset}>
              {MOTION_LABELS[preset]}
            </option>
          ))}
        </select>
      </label>
    </div>
  );
}

export function PrecisionLegend() {
  return (
    <div className="rounded-xl border border-slate-700/80 bg-slate-900/85 px-3 py-2 text-[11px] text-slate-300 shadow-lg shadow-black/30 backdrop-blur">
      <p className="flex items-center gap-2">
        <span
          aria-hidden="true"
          className="size-2.5 rounded-full bg-sky-400 ring-2 ring-sky-400/30"
        />
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

const DOWNLOADS: { kind: DownloadKind; label: string; hint: string }[] = [
  { kind: 'pdf', label: 'Reporte (PDF)', hint: 'Portada, resumen, mapa, gráficas y noticias' },
  { kind: 'csv', label: 'Datos (CSV)', hint: 'Una fila por nota, para Excel' },
  { kind: 'geojson', label: 'Mapa de puntos (GeoJSON)', hint: 'Para QGIS o Google Earth' },
  { kind: 'print', label: 'Imprimir', hint: 'Abre el reporte en otra pestaña' },
];

/**
 * Descargas de la búsqueda abierta (§15, ADR-0018). Se activan cuando la
 * búsqueda termina; mientras se genera un archivo, su botón dice "Generando…".
 */
export function DownloadsPanel() {
  const searchId = useExplorerStore((s) => s.searchId);
  const search = useSearch(searchId).data;
  const ready = search !== undefined && isFinished(search.status);
  const downloads = useDownloads(ready ? searchId : null);
  return (
    <section aria-label="Descargas" className={`${GLASS} space-y-2 p-4`}>
      <h2 className={PANEL_TITLE}>Descargas</h2>
      {DOWNLOADS.map(({ kind, label, hint }) => (
        <button
          key={kind}
          type="button"
          disabled={!ready || downloads.running !== null}
          title={hint}
          onClick={() => {
            downloads.start(kind);
          }}
          className={`${SMALL_BUTTON} flex w-full items-center justify-between py-2 ${
            kind === 'pdf' ? 'border-sky-400/40 bg-sky-500/15 text-sky-100' : ''
          }`}
        >
          <span>{downloads.running === kind ? 'Generando…' : label}</span>
          {downloads.running === kind && (
            <span
              aria-hidden="true"
              className="size-3 animate-spin rounded-full border-2 border-slate-500 border-t-sky-300"
            />
          )}
        </button>
      ))}
      {downloads.error && (
        <p role="alert" className="text-[11px] text-rose-300">
          {downloads.error.message}
        </p>
      )}
      <p className="text-[11px] text-slate-500">
        {ready
          ? 'El primer reporte de una búsqueda escribe un resumen con IA (~0.001 USD); los siguientes no cuestan.'
          : 'Disponibles cuando la búsqueda termine.'}
      </p>
    </section>
  );
}
