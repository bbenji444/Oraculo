/**
 * Tarjeta con el estado de un componente: insignia con pulso, latido,
 * descripción, latencia, versiones y, si falló, qué pasó.
 *
 * Diseño «consola táctica» (ADR-0036): panel con borde de luz que sigue al
 * mouse; entra escalonada según `index`.
 */
import type { CSSProperties } from 'react';

import type { ComponentHealth } from '../../services/health';
import { Heartbeat } from '../ui/Heartbeat';
import { HudChip } from '../ui/HudChip';
import { HudPanel } from '../ui/HudPanel';
import { componentLabel } from './componentLabels';

interface ComponentCardProps {
  component: ComponentHealth;
  /** Posición en la lista: entra un poco después de la anterior. */
  index?: number;
}

// Retraso entre los latidos de tarjetas vecinas, para que no laten juntos.
const BEAT_STAGGER_S = 0.35;

export function ComponentCard({ component, index = 0 }: ComponentCardProps) {
  const label = componentLabel(component.name);
  const isOk = component.status === 'ok';
  const infoEntries = Object.entries(component.info);

  return (
    <HudPanel
      className={`hud-reveal p-5 ${isOk ? '' : 'border-rose-500/40'}`}
      style={{ '--i': index } as CSSProperties}
    >
      <article aria-label={`${label.title}: ${isOk ? 'funcionando' : 'con error'}`}>
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <h3 className="font-display text-sm tracking-[0.14em] text-slate-50 uppercase">
              {label.title}
            </h3>
            <p className="mt-1 text-sm text-slate-400">{label.description}</p>
          </div>
          <HudChip tone={isOk ? 'green' : 'rose'} live={isOk} dot>
            {isOk ? 'Funcionando' : 'Con error'}
          </HudChip>
        </div>

        <Heartbeat ok={isOk} delaySeconds={index * BEAT_STAGGER_S} className="mt-4" />

        {component.detail && <p className="mt-3 text-sm text-rose-200">{component.detail}</p>}

        <dl className="mt-3 flex flex-wrap gap-2 text-xs">
          {component.latency_ms !== null && (
            <div className="rounded-md border border-sky-400/15 bg-sky-400/5 px-2 py-1 text-slate-200">
              <dt className="inline font-display text-[9px] tracking-[0.16em] text-sky-300/70 uppercase">
                respuesta{' '}
              </dt>
              <dd className="inline tabular-nums">{component.latency_ms.toFixed(1)} ms</dd>
            </div>
          )}
          {infoEntries.map(([key, value]) => (
            <div
              key={key}
              className="rounded-md border border-sky-400/15 bg-sky-400/5 px-2 py-1 text-slate-200"
            >
              <dt className="inline font-display text-[9px] tracking-[0.16em] text-sky-300/70 uppercase">
                {key}{' '}
              </dt>
              <dd className="inline">{value}</dd>
            </div>
          ))}
        </dl>
      </article>
    </HudPanel>
  );
}
