/**
 * Resultados de la pestaña "Notas": la consulta en palabras, los conteos por
 * día y por fuente, y la lista de notas con su link al medio.
 *
 * Solo muestra título, medio, fecha, fragmento y link: nunca el artículo
 * (CLAUDE.md §8). Las notas de GDELT se citan con su crédito y link.
 */
import { type LocalIndexSearch, sourceLabel } from '../../services/localIndex';
import { formatMexicoCity } from './format';

interface NotesResultsProps {
  result: LocalIndexSearch;
}

export function NotesResults({ result }: NotesResultsProps) {
  return (
    <section aria-label="Resultados" className="space-y-3">
      <div className="rounded-lg border border-slate-800 bg-slate-950/60 p-3 text-xs">
        <p className="text-slate-300">
          <span className="font-semibold text-slate-100">
            {result.total.toLocaleString('es-MX')} notas
          </span>{' '}
          · {result.concept_name} · {result.region} · {result.period}
        </p>
        <p className="mt-1 font-mono text-slate-400">{result.query_text}</p>
        {result.message && <p className="mt-1 text-amber-300">{result.message}</p>}
        <div className="mt-2 flex flex-wrap gap-1.5">
          {result.by_day.map((day) => (
            <span key={day.label} className="rounded bg-slate-800 px-1.5 py-0.5 text-slate-300">
              {day.label}: {day.count}
            </span>
          ))}
          {result.by_source.map((source) => (
            <span
              key={source.label}
              className="rounded bg-sky-500/10 px-1.5 py-0.5 text-sky-200 ring-1 ring-sky-500/30"
            >
              {sourceLabel(source.label)}: {source.count}
            </span>
          ))}
        </div>
      </div>

      {result.total === 0 ? (
        <p className="text-sm text-slate-400">
          No hay notas en el índice para esta búsqueda. El índice crece cada 15 minutos mientras los
          servicios están encendidos.
        </p>
      ) : (
        <ol className="space-y-2">
          {result.notes.map((note) => (
            <li key={note.url} className="rounded-lg border border-slate-800 bg-slate-900/60 p-3">
              <a
                href={note.url}
                target="_blank"
                rel="noreferrer"
                className="text-sm font-medium text-slate-100 hover:text-sky-300 hover:underline"
              >
                {note.title}
              </a>
              <p className="mt-1 text-xs text-slate-400">
                {note.source_domain ?? 'medio desconocido'}
                {note.published_at && ` · ${formatMexicoCity(note.published_at)}`} ·{' '}
                {sourceLabel(note.source)}
              </p>
              {note.snippet && <p className="mt-1 text-xs text-slate-300">{note.snippet}</p>}
            </li>
          ))}
        </ol>
      )}

      <p className="text-[11px] text-slate-500">
        Datos de notas de{' '}
        <a
          href="https://www.gdeltproject.org/"
          target="_blank"
          rel="noreferrer"
          className="underline hover:text-slate-300"
        >
          The GDELT Project
        </a>
        . Son candidatas: la Fase 4 confirma su ubicación con el catálogo INEGI.
      </p>
    </section>
  );
}
