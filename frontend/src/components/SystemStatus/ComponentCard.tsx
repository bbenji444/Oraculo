/**
 * Tarjeta con el estado de un componente: semáforo, descripción, latencia,
 * versiones y, si falló, qué pasó.
 */
import type { ComponentHealth } from '../../services/health';
import { componentLabel } from './componentLabels';

interface ComponentCardProps {
  component: ComponentHealth;
}

export function ComponentCard({ component }: ComponentCardProps) {
  const label = componentLabel(component.name);
  const isOk = component.status === 'ok';
  const infoEntries = Object.entries(component.info);

  return (
    <article
      className={`rounded-xl border p-4 transition-colors ${
        isOk ? 'border-slate-800 bg-slate-900/60' : 'border-rose-900/70 bg-rose-950/30'
      }`}
      aria-label={`${label.title}: ${isOk ? 'funcionando' : 'con error'}`}
    >
      <div className="flex items-start justify-between gap-3">
        <div>
          <h3 className="font-medium text-slate-100">{label.title}</h3>
          <p className="mt-0.5 text-sm text-slate-400">{label.description}</p>
        </div>
        <span
          className={`inline-flex shrink-0 items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium ${
            isOk ? 'bg-emerald-500/10 text-emerald-300' : 'bg-rose-500/10 text-rose-300'
          }`}
        >
          <span
            aria-hidden="true"
            className={`size-2 rounded-full ${isOk ? 'bg-emerald-400' : 'bg-rose-400'}`}
          />
          {isOk ? 'Funcionando' : 'Con error'}
        </span>
      </div>

      {component.detail && <p className="mt-3 text-sm text-rose-200">{component.detail}</p>}

      <dl className="mt-3 flex flex-wrap gap-2 text-xs">
        {component.latency_ms !== null && (
          <div className="rounded-md bg-slate-800/70 px-2 py-1 text-slate-300">
            <dt className="inline text-slate-500">respuesta </dt>
            <dd className="inline tabular-nums">{component.latency_ms.toFixed(1)} ms</dd>
          </div>
        )}
        {infoEntries.map(([key, value]) => (
          <div key={key} className="rounded-md bg-slate-800/70 px-2 py-1 text-slate-300">
            <dt className="inline text-slate-500">{key} </dt>
            <dd className="inline">{value}</dd>
          </div>
        ))}
      </dl>
    </article>
  );
}
