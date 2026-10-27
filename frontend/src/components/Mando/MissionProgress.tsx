/**
 * Avance del barrido en la consola de misión (diseño «Centro de mando»): la
 * etapa en curso descifrándose, el porcentaje, un cronómetro, un riel con las
 * ocho etapas del pipeline que se van encendiendo y una bitácora con los
 * números que ya se conocen.
 *
 * Recibe la búsqueda ya consultada (se renueva sola mientras corre); no pide
 * nada por su cuenta.
 */
import type { CSSProperties } from 'react';

import { useNow } from '../../hooks/useNow';
import type { Search } from '../../services/searches';
import { STAGES, stageProgress } from '../Explore/format';
import { CountUp } from '../ui/CountUp';
import { DecodeText } from '../ui/DecodeText';
import { elapsedLabel, missionLog, STAGE_SHORT, stageIndex } from './mission';

// Renglones de la bitácora a la vista: los últimos, para no crecer la consola.
const LOG_LINES = 3;

/** Cronómetro aparte: así solo él se vuelve a dibujar cada segundo. */
function Elapsed({ start }: { start: string | null }) {
  const now = useNow();
  return <span className="mando-clock text-[15px]">{elapsedLabel(start, now)}</span>;
}

function nodeState(i: number, current: number, failed: boolean): string {
  if (i < current) return 'done';
  if (i === current) return failed ? 'failed' : 'active';
  return 'todo';
}

export function MissionProgress({ search }: { search: Search }) {
  const current = stageIndex(search);
  const { label, percent } = stageProgress(search.progress, search.status);
  const failed = search.status === 'failed';
  const last = STAGES.length - 1;
  // El riel se llena hasta el nodo de la etapa en curso.
  const fill = Math.min(1, current / last);
  const log = missionLog(search).slice(-LOG_LINES);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div className="min-w-0" aria-live="polite">
          <p className="hud-kpi-label">
            Etapa {Math.min(current + 1, STAGES.length)} de {STAGES.length}
          </p>
          <p
            className={`mt-1.5 truncate text-[15px] font-semibold ${
              failed ? 'text-rose-300' : 'text-slate-50'
            }`}
          >
            {/* key: cada etapa nueva entra descifrándose. */}
            <DecodeText key={label} text={label} onHover={false} />
          </p>
        </div>
        <div className="flex items-end gap-6 text-right">
          <div>
            <p className="hud-kpi-label">Tiempo</p>
            <p className="mt-1.5">
              <Elapsed start={search.started_at ?? search.created_at} />
            </p>
          </div>
          <div>
            <p className="hud-kpi-label">Avance</p>
            <p
              className="hud-kpi-value mt-1 text-[1.7rem]"
              role="progressbar"
              aria-valuenow={percent}
              aria-valuemin={0}
              aria-valuemax={100}
              aria-label="Avance del barrido"
            >
              <CountUp value={percent} format={(value) => `${String(Math.round(value))}%`} />
            </p>
          </div>
        </div>
      </div>

      <div className="relative" style={{ '--rail-n': STAGES.length } as CSSProperties}>
        <span aria-hidden="true" className="mando-rail-track">
          <span className="mando-rail-fill" style={{ '--rail-progress': fill } as CSSProperties} />
        </span>
        <ol className="mando-rail" aria-label="Etapas del barrido">
          {STAGES.map((stage, i) => (
            <li
              key={stage}
              className="mando-node"
              data-state={nodeState(i, current, failed)}
              aria-current={i === current ? 'step' : undefined}
            >
              <span aria-hidden="true" className="mando-node-dot" />
              {STAGE_SHORT[stage] ?? stage}
            </li>
          ))}
        </ol>
      </div>

      <ul
        aria-label="Bitácora del barrido"
        className="space-y-1 font-mono text-[11.5px] text-slate-300"
      >
        {log.map((line) => (
          <li key={line} className="mando-log-line truncate">
            <span aria-hidden="true" className="text-sky-400">
              ›{' '}
            </span>
            {line}
          </li>
        ))}
      </ul>
      {search.error_summary && <p className="text-[11px] text-amber-200">{search.error_summary}</p>}
    </div>
  );
}
