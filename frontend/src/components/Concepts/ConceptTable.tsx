/**
 * Tabla de conceptos: color, nombre, palabras clave y estado.
 *
 * El interruptor de "Activo" cambia el estado al instante, sin abrir el
 * formulario. Clic en una fila la abre para editar.
 */
import type { Concept } from '../../services/concepts';

interface ConceptTableProps {
  concepts: Concept[];
  selectedId: number | null;
  onSelect: (concept: Concept) => void;
  onToggleActive: (concept: Concept) => void;
  /** Concepto cuyo cambio de estado está en curso. */
  togglingId: number | null;
}

// Cuántas palabras clave se muestran antes de "+N".
const VISIBLE_KEYWORDS = 3;

export function ConceptTable({
  concepts,
  selectedId,
  onSelect,
  onToggleActive,
  togglingId,
}: ConceptTableProps) {
  return (
    <table className="w-full table-fixed text-left text-sm">
      <caption className="sr-only">Conceptos de búsqueda</caption>
      <thead className="text-xs uppercase tracking-wide text-slate-500">
        <tr>
          <th scope="col" className="px-3 py-2 font-medium">
            Concepto
          </th>
          <th scope="col" className="hidden px-3 py-2 font-medium md:table-cell">
            Palabras clave
          </th>
          <th scope="col" className="w-28 px-3 py-2 text-right font-medium">
            Activo
          </th>
        </tr>
      </thead>
      <tbody className="divide-y divide-slate-800/80">
        {concepts.map((concept) => {
          const hidden = concept.keywords.length - VISIBLE_KEYWORDS;
          return (
            <tr
              key={concept.id}
              onClick={() => {
                onSelect(concept);
              }}
              className={`cursor-pointer transition-colors ${
                selectedId === concept.id ? 'bg-sky-500/10' : 'hover:bg-slate-900'
              } ${concept.is_active ? '' : 'opacity-60'}`}
            >
              <td className="px-3 py-3">
                <button
                  type="button"
                  onClick={(event) => {
                    event.stopPropagation();
                    onSelect(concept);
                  }}
                  className="flex w-full items-start gap-3 text-left focus-visible:outline-2 focus-visible:outline-sky-400"
                >
                  <span
                    aria-hidden="true"
                    style={{ backgroundColor: concept.color }}
                    className="mt-1 size-3 shrink-0 rounded-full"
                  />
                  <span className="min-w-0">
                    <span className="block truncate font-medium text-slate-100">
                      {concept.name}
                    </span>
                    <span className="block truncate text-xs text-slate-400">
                      {concept.description || 'Sin descripción'}
                    </span>
                  </span>
                </button>
              </td>
              <td className="hidden px-3 py-3 md:table-cell">
                <span className="flex flex-wrap gap-1">
                  {concept.keywords.slice(0, VISIBLE_KEYWORDS).map((keyword) => (
                    <span
                      key={keyword}
                      className="truncate rounded bg-slate-800 px-1.5 py-0.5 text-xs text-slate-300"
                    >
                      {keyword}
                    </span>
                  ))}
                  {hidden > 0 && (
                    <span className="px-1 py-0.5 text-xs text-slate-500">+{hidden}</span>
                  )}
                </span>
              </td>
              <td className="px-3 py-3 text-right">
                <button
                  type="button"
                  role="switch"
                  aria-checked={concept.is_active}
                  aria-label={`${concept.is_active ? 'Desactivar' : 'Activar'} «${concept.name}»`}
                  disabled={togglingId === concept.id}
                  onClick={(event) => {
                    event.stopPropagation();
                    onToggleActive(concept);
                  }}
                  className={`relative inline-flex h-5 w-9 shrink-0 items-center rounded-full transition-colors focus-visible:outline-2 focus-visible:outline-sky-400 disabled:opacity-50 ${
                    concept.is_active ? 'bg-emerald-500' : 'bg-slate-700'
                  }`}
                >
                  <span
                    className={`inline-block size-4 rounded-full bg-white shadow transition-transform ${
                      concept.is_active ? 'translate-x-4' : 'translate-x-0.5'
                    }`}
                  />
                </button>
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
