/**
 * Laboratorio del muro (Fase 9.1, ADR-0102): compara cómo dibujar nodos que
 * brillan y arcos de luz sobre el **mismo** globo de Explorar, con fps medidos.
 *
 * Solo para desarrollo: se abre con `?laboratorio` en la URL (pestaña
 * "Laboratorio") y se carga aparte, así no pesa en Explorar.
 *
 * - Opción: sin muro (control), A (MapLibre propio) o B (deck.gl).
 * - Caso: el de prueba de Polanco (sin nombres reales) o sintéticos de 25, 150
 *   y 500 nodos.
 * - "Correr guion": 1 vuelta de calentamiento (carga teselas) y 3 medidas de
 *   cada paso (`labScript.ts`). La tabla acumula los resultados y también
 *   quedan en `window.__labResults` para copiarlos al ADR.
 *
 * No hace: no guarda nada ni llama a la API.
 */
import { Map as MapLibreMap } from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import { useEffect, useMemo, useRef, useState } from 'react';

import { GLASS, PANEL_TITLE, SMALL_BUTTON } from '../components/Explore/ui';
import { SpaceBackground } from '../components/Space/SpaceBackground';
import { setupMapLibre } from '../map/setup';
import { buildMapStyle } from '../map/style';
import { useCameraStore } from '../store/camera';
import { type FrameStats, FRAME_BUDGET_MS, summarizeRuns } from './fpsMeter';
import { DEMO_CASE, type LabCase, syntheticCase } from './labCase';
import { PHASE_LABEL, PHASES, type Phase, runPhase } from './labScript';
import { addDeckMuro } from './muroDeck';
import type { MuroEngine } from './muroLabels';
import { addMapLibreMuro } from './muroMapLibre';

type EngineKey = 'control' | 'maplibre' | 'deck';
type CaseKey = 'demo' | '25' | '150' | '500';

const ENGINES: { key: EngineKey; label: string }[] = [
  { key: 'control', label: 'Sin muro (control)' },
  { key: 'maplibre', label: 'A · MapLibre propio' },
  { key: 'deck', label: 'B · deck.gl 9.4' },
];
const CASES: { key: CaseKey; label: string }[] = [
  { key: 'demo', label: 'Caso de prueba (9 nodos)' },
  { key: '25', label: '25 nodos' },
  { key: '150', label: '150 nodos' },
  { key: '500', label: '500 nodos' },
];
// Una vuelta de calentamiento y tres medidas, como en el plan de la 9.1.
const MEASURED_RUNS = 3;

export interface LabResult {
  engine: EngineKey;
  size: CaseKey;
  phase: Phase;
  runs: FrameStats[];
  summary: FrameStats | null;
}

function caseFor(key: CaseKey): LabCase {
  return key === 'demo' ? DEMO_CASE : syntheticCase(Number(key));
}

function addEngine(map: MapLibreMap, key: EngineKey, labCase: LabCase): MuroEngine | null {
  if (key === 'maplibre') return addMapLibreMuro(map, labCase);
  if (key === 'deck') return addDeckMuro(map, labCase);
  return null;
}

/** Verde si cumple el criterio de la 9.1, ámbar si no. */
function verdict(stats: FrameStats | null): string {
  if (!stats) return 'text-slate-400';
  const ok = stats.fps >= 58 && stats.p95Ms <= 20 && stats.slowShare < 0.05;
  return ok ? 'text-emerald-300' : 'text-amber-300';
}

export default function MuroLab() {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MapLibreMap | null>(null);
  const engineRef = useRef<MuroEngine | null>(null);
  const [ready, setReady] = useState(false);
  const [engine, setEngine] = useState<EngineKey>('maplibre');
  const [size, setSize] = useState<CaseKey>('demo');
  const [status, setStatus] = useState('');
  const [running, setRunning] = useState(false);
  const [results, setResults] = useState<LabResult[]>([]);
  const labCase = useMemo(() => caseFor(size), [size]);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    setupMapLibre();
    const map = new MapLibreMap({
      container,
      style: buildMapStyle(window.location.origin, 'night'),
      center: [-102, 23.5],
      zoom: 2.2,
      attributionControl: { compact: true },
    });
    // El fondo de estrellas sigue a la cámara, como en Explorar.
    const onMove = () => {
      const center = map.getCenter();
      useCameraStore.getState().setView({
        lng: center.lng,
        lat: center.lat,
        zoom: map.getZoom(),
        bearing: map.getBearing(),
        pitch: map.getPitch(),
      });
    };
    map.on('move', onMove);
    map.on('load', () => {
      setReady(true);
    });
    mapRef.current = map;
    (window as unknown as { __mapa?: MapLibreMap }).__mapa = map;
    return () => {
      engineRef.current?.remove();
      engineRef.current = null;
      map.remove();
      mapRef.current = null;
    };
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    engineRef.current?.remove();
    engineRef.current = addEngine(map, engine, labCase);
    return () => {
      engineRef.current?.remove();
      engineRef.current = null;
    };
  }, [engine, labCase, ready]);

  const runScript = async () => {
    const map = mapRef.current;
    if (!map) return;
    setRunning(true);
    const found: LabResult[] = [];
    for (const phase of PHASES) {
      setStatus(`${PHASE_LABEL[phase]}: calentando…`);
      await runPhase(map, labCase, phase);
      const runs: FrameStats[] = [];
      for (let i = 0; i < MEASURED_RUNS; i += 1) {
        setStatus(`${PHASE_LABEL[phase]}: medida ${String(i + 1)} de ${String(MEASURED_RUNS)}`);
        runs.push(await runPhase(map, labCase, phase));
      }
      found.push({ engine, size, phase, runs, summary: summarizeRuns(runs) });
    }
    setResults((previous) => {
      const next = [...previous, ...found];
      (window as unknown as { __labResults?: LabResult[] }).__labResults = next;
      return next;
    });
    setStatus('Listo.');
    setRunning(false);
  };

  return (
    <div className="relative h-full overflow-hidden bg-[#02030a]">
      <SpaceBackground />
      {/* Envoltorio: el CSS de MapLibre pone position: relative al contenedor del mapa. */}
      <div className="absolute inset-0">
        <div ref={containerRef} className="h-full w-full" aria-label="Globo del laboratorio" />
      </div>
      <section
        aria-label="Laboratorio del muro"
        className={`${GLASS} absolute left-4 top-4 w-[26rem] max-h-[calc(100%-2rem)] space-y-3 overflow-y-auto p-4 text-sm`}
      >
        <div>
          <h2 className={PANEL_TITLE}>Laboratorio del muro · 9.1</h2>
          <p className="mt-1 text-xs text-slate-400">
            Mismo globo de Explorar. Compara opciones con el mismo guion de cámara. Meta: ≥ 58 fps,
            p95 ≤ 20 ms y menos de 5 % de cuadros de más de {FRAME_BUDGET_MS.toFixed(1)} ms.
          </p>
        </div>
        <div className="grid grid-cols-2 gap-2">
          <label className="text-xs text-slate-400">
            Opción
            <select
              value={engine}
              disabled={running}
              onChange={(event) => {
                setEngine(event.target.value as EngineKey);
              }}
              className="mt-1 w-full rounded-md bg-slate-800 px-2 py-1 text-sm text-slate-100"
            >
              {ENGINES.map((e) => (
                <option key={e.key} value={e.key}>
                  {e.label}
                </option>
              ))}
            </select>
          </label>
          <label className="text-xs text-slate-400">
            Caso
            <select
              value={size}
              disabled={running}
              onChange={(event) => {
                setSize(event.target.value as CaseKey);
              }}
              className="mt-1 w-full rounded-md bg-slate-800 px-2 py-1 text-sm text-slate-100"
            >
              {CASES.map((c) => (
                <option key={c.key} value={c.key}>
                  {c.label}
                </option>
              ))}
            </select>
          </label>
        </div>
        <button
          type="button"
          disabled={!ready || running}
          onClick={() => {
            void runScript();
          }}
          className="w-full rounded-xl bg-gradient-to-r from-sky-500 to-cyan-400 px-4 py-2 text-sm font-semibold text-slate-950 disabled:from-slate-600 disabled:to-slate-600 disabled:text-slate-300"
        >
          {running ? 'Midiendo…' : 'Correr guion'}
        </button>
        {status && (
          <p aria-live="polite" className="text-xs text-slate-300">
            {status}
          </p>
        )}
        {results.length > 0 && (
          <table className="w-full text-left text-xs">
            <thead className="text-slate-400">
              <tr>
                <th className="py-1 font-medium">Opción · caso</th>
                <th className="font-medium">Paso</th>
                <th className="text-right font-medium">fps</th>
                <th className="text-right font-medium">p95</th>
                <th className="text-right font-medium">lentos</th>
              </tr>
            </thead>
            <tbody>
              {results.map((r) => (
                <tr key={`${r.engine}-${r.size}-${r.phase}`} className="border-t border-white/5">
                  <td className="py-1 text-slate-300">
                    {r.engine} · {r.size}
                  </td>
                  <td className="text-slate-300">{PHASE_LABEL[r.phase]}</td>
                  <td className={`text-right tabular-nums ${verdict(r.summary)}`}>
                    {r.summary?.fps ?? '—'}
                  </td>
                  <td className="text-right tabular-nums text-slate-300">
                    {r.summary?.p95Ms ?? '—'}
                  </td>
                  <td className="text-right tabular-nums text-slate-300">
                    {r.summary ? `${(r.summary.slowShare * 100).toFixed(1)} %` : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {results.length > 0 && (
          <button
            type="button"
            className={SMALL_BUTTON}
            onClick={() => {
              void navigator.clipboard.writeText(JSON.stringify(results, null, 2));
            }}
          >
            Copiar resultados (JSON)
          </button>
        )}
      </section>
    </div>
  );
}
