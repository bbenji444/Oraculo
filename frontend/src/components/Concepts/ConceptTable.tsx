/**
 * Tabla de conceptos: color, nombre, palabras clave y estado.
 *
 * El interruptor de "Activo" cambia el estado al instante, sin abrir el
 * formulario. Clic en una fila la abre para editar.
 *
 * Diseño «consola táctica» (ADR-0036): la fila se ilumina con una barra de luz
 * a la izquierda; las palabras clave son insignias y el interruptor brilla.
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
      <thead className="font-display text-[9.5px] tracking-[0.22em] text-sky-300/70 uppercase">
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
      <tbody className="divide-y divide-sky-400/10">
        {concepts.map((concept) => {
          const hidden = concept.keywords.length - VISIBLE_KEYWORDS;
          return (
            <tr
              key={concept.id}
              onClick={() => {
                onSelect(concept);
              }}
              aria-current={selectedId === concept.id}
              className={`hud-trow ${concept.is_active ? '' : 'opacity-60'}`}
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
                    className="mt-1 size-3 shrink-0 rounded-full shadow-[0_0_10px_currentColor]"
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
                      className="truncate rounded-md border border-sky-400/20 bg-sky-400/5 px-1.5 py-0.5 text-xs text-slate-200"
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
                  className="hud-switch inline-block align-middle focus-visible:outline-2 focus-visible:outline-sky-400 disabled:opacity-50"
                />
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
