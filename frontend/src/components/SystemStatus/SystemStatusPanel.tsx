/**
 * Panel "Estado del sistema": resumen general y una tarjeta por componente.
 *
 * Con el diseño «consola táctica» (ADR-0036): el resumen es un panel con
 * radar y el conteo de componentes en línea; cada componente, una tarjeta con
 * su latido.
 *
 * Obtiene los datos con useHealth (nunca llama a fetch directamente).
 */
import { useHealth } from '../../hooks/useHealth';
import { CountUp } from '../ui/CountUp';
import { HudButton } from '../ui/HudButton';
import { HudPanel } from '../ui/HudPanel';
import { SectionHeading } from '../ui/SectionHeading';
import { ComponentCard } from './ComponentCard';

export function SystemStatusPanel() {
  const { data, error, isPending, isFetching, refetch } = useHealth();
  const online = data?.components.filter((c) => c.status === 'ok').length ?? 0;
  const allOk = data?.status === 'ok';

  return (
    <section aria-labelledby="estado-titulo" className="mx-auto w-full max-w-5xl px-4 py-8 sm:px-6">
      <div id="estado-titulo">
        <SectionHeading
          kicker="Diagnóstico · cada 10 segundos"
          title="Estado del sistema"
          description="Se actualiza solo. Si algo falla, aquí se explica qué."
          actions={
            <HudButton onClick={() => void refetch()} disabled={isFetching}>
              {isFetching ? 'Revisando…' : 'Revisar ahora'}
            </HudButton>
          }
        />
      </div>

      <div role="status" aria-live="polite" className="mt-8">
        {isPending && <p className="text-slate-400">Revisando componentes…</p>}

        {error && (
          <HudPanel className="border-rose-500/40 p-4 text-rose-200">{error.message}</HudPanel>
        )}

        {data && (
          <>
            <HudPanel scan className="mb-5 flex flex-wrap items-center gap-5 p-5">
              <span aria-hidden="true" className={`hud-radar ${allOk ? '' : 'hud-radar--warn'}`} />
              <div className="min-w-0 flex-1 basis-60">
                <p
                  className={`font-display text-[10px] tracking-[0.28em] ${
                    allOk ? 'text-emerald-300' : 'text-amber-300'
                  }`}
                >
                  {allOk ? 'SISTEMA EN LÍNEA' : 'ATENCIÓN'}
                </p>
                <p className="mt-1 text-base text-slate-50">
                  {allOk
                    ? 'Todos los componentes funcionan.'
                    : 'Hay componentes con problemas: las búsquedas podrían no funcionar.'}
                </p>
              </div>
              <div className="text-right">
                <p className="hud-kpi-value">
                  <CountUp value={online} />
                  <span className="text-slate-500">/{data.components.length}</span>
                </p>
                <p className="hud-kpi-label mt-2">en línea</p>
              </div>
            </HudPanel>
            <div className="grid gap-4 sm:grid-cols-2">
              {data.components.map((component, i) => (
                <ComponentCard key={component.name} component={component} index={i} />
              ))}
            </div>
          </>
        )}
      </div>
    </section>
  );
}
