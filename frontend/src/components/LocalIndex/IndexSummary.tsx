/**
 * Resumen del índice local: cuántas notas hay por fuente y cuándo corrió la
 * ingesta por última vez. Se refresca solo cada minuto (useIndexStats).
 */
import { useIndexStats } from '../../hooks/useLocalIndex';
import { sourceLabel } from '../../services/localIndex';
import { formatMexicoCity } from './format';

export function IndexSummary() {
  const stats = useIndexStats();

  if (stats.isPending) return <p className="text-xs text-slate-500">Cargando el índice…</p>;
  if (stats.error) {
    return (
      <p role="alert" className="text-xs text-rose-300">
        No se pudo leer el índice: {stats.error.message}
      </p>
    );
  }
  const data = stats.data;
  return (
    <div className="flex flex-wrap items-center gap-2 text-xs">
      <span className="font-medium text-slate-200">
        {data.total_notes.toLocaleString('es-MX')} notas en el índice
      </span>
      {data.sources.map((source) => (
        <span
          key={source.source}
          className="rounded-md bg-slate-800/80 px-2 py-0.5 text-slate-300 ring-1 ring-slate-700"
        >
          {sourceLabel(source.source)}: {source.notes.toLocaleString('es-MX')}
        </span>
      ))}
      <span className="text-slate-500">
        {data.total_mb.toLocaleString('es-MX')} MB en disco · última ingesta{' '}
        {data.last_run_at ? formatMexicoCity(data.last_run_at) : 'todavía no'}
      </span>
    </div>
  );
}
