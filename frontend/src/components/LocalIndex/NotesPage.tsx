/**
 * Pestaña temporal "Notas": ver ya las notas reales del índice local.
 *
 * Junta el resumen, el formulario y los resultados; la búsqueda la hace
 * useLocalIndexSearch. La Fase 6 la reemplaza por el globo con resultados
 * (ADR-0014).
 */
import { useLocalIndexSearch } from '../../hooks/useLocalIndex';
import { IndexSummary } from './IndexSummary';
import { NotesResults } from './NotesResults';
import { NotesSearchForm } from './NotesSearchForm';

export function NotesPage() {
  const search = useLocalIndexSearch();

  return (
    <div className="mx-auto max-w-4xl space-y-4 p-4 sm:p-6">
      <section
        aria-labelledby="notas-titulo"
        className="space-y-3 rounded-xl border border-slate-800 bg-slate-900/60 p-4"
      >
        <div>
          <h2 id="notas-titulo" className="text-sm font-semibold text-slate-100">
            Notas del índice local
          </h2>
          <p className="mt-0.5 text-xs text-slate-400">
            Vista de prueba: busca un concepto en las notas que el sistema junta solo cada 15
            minutos. Gratis, sin créditos. La búsqueda sobre el globo llega en la Fase 6.
          </p>
        </div>
        <IndexSummary />
        <NotesSearchForm
          searching={search.isPending}
          onSearch={(args) => {
            search.mutate(args);
          }}
        />
      </section>

      {search.error && (
        <p role="alert" className="rounded-lg bg-rose-500/10 px-3 py-2 text-sm text-rose-200">
          {search.error.message}
        </p>
      )}
      {search.data && <NotesResults result={search.data} />}
    </div>
  );
}
