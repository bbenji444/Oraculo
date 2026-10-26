/**
 * Panel "Estado del sistema": resumen general y una tarjeta por componente.
 *
 * Obtiene los datos con useHealth (nunca llama a fetch directamente).
 */
import { useHealth } from '../../hooks/useHealth';
import { ComponentCard } from './ComponentCard';

export function SystemStatusPanel() {
  const { data, error, isPending, isFetching, refetch } = useHealth();

  return (
    <section aria-labelledby="estado-titulo" className="mx-auto w-full max-w-4xl px-6 py-8">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h2 id="estado-titulo" className="titulo-oraculo text-base font-bold text-sky-50">
            Estado del sistema
          </h2>
          <p className="mt-1 text-sm text-slate-400">
            Se actualiza solo cada 10 segundos. Si algo falla, aquí se explica qué.
          </p>
        </div>
        <button
          type="button"
          onClick={() => void refetch()}
          disabled={isFetching}
          className="rounded-lg border border-slate-700 px-3 py-1.5 text-sm text-slate-200 hover:bg-slate-800 focus-visible:outline-2 focus-visible:outline-sky-400 disabled:opacity-50"
        >
          {isFetching ? 'Revisando…' : 'Revisar ahora'}
        </button>
      </div>

      <div role="status" aria-live="polite" className="mt-6">
        {isPending && <p className="text-slate-400">Revisando componentes…</p>}

        {error && (
          <div className="rounded-xl border border-rose-900/70 bg-rose-950/30 p-4 text-rose-200">
            {error.message}
          </div>
        )}

        {data && (
          <>
            <div
              className={`mb-4 flex items-center gap-3 rounded-xl px-4 py-3 ${
                data.status === 'ok'
                  ? 'bg-emerald-500/10 text-emerald-200'
                  : 'bg-amber-500/10 text-amber-200'
              }`}
            >
              <span
                aria-hidden="true"
                className={`size-2.5 rounded-full ${
                  data.status === 'ok' ? 'bg-emerald-400' : 'bg-amber-400'
                }`}
              />
              {data.status === 'ok'
                ? 'Todos los componentes funcionan.'
                : 'Hay componentes con problemas: las búsquedas podrían no funcionar.'}
            </div>
            <div className="grid gap-3 sm:grid-cols-2">
              {data.components.map((component) => (
                <ComponentCard key={component.name} component={component} />
              ))}
            </div>
          </>
        )}
      </div>
    </section>
  );
}
