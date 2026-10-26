/**
 * Pantalla "Conceptos" (especificación §14.1, historia H2).
 *
 * A la izquierda la tabla de conceptos; a la derecha el formulario para
 * crear o editar, con "Probar concepto" debajo. Los datos llegan por los
 * hooks de TanStack Query; esta pantalla no hace llamadas HTTP.
 */
import { useState } from 'react';

import { useConcepts, useUpdateConcept } from '../../hooks/useConcepts';
import type { Concept } from '../../services/concepts';
import { ConceptForm } from './ConceptForm';
import { ConceptTable } from './ConceptTable';

/** Qué muestra el panel derecho: nada, un concepto nuevo o uno existente. */
type Editing = { kind: 'none' } | { kind: 'new' } | { kind: 'edit'; id: number };

export function ConceptsPage() {
  const concepts = useConcepts();
  const toggle = useUpdateConcept();
  const [editing, setEditing] = useState<Editing>({ kind: 'none' });
  const list = concepts.data ?? [];
  const selected = editing.kind === 'edit' ? list.find((c) => c.id === editing.id) : undefined;
  const activeCount = list.filter((c) => c.is_active).length;

  function close() {
    setEditing({ kind: 'none' });
  }

  return (
    <div className="mx-auto grid max-w-7xl gap-6 px-4 py-6 sm:px-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,32rem)]">
      <section aria-labelledby="conceptos-titulo" className="min-w-0">
        <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
          <div>
            <h2 id="conceptos-titulo" className="titulo-oraculo text-base font-bold text-sky-50">
              Conceptos
            </h2>
            <p className="text-sm text-slate-400">
              Plantillas de búsqueda: palabras clave, exclusiones y color.
              {concepts.isSuccess && ` ${String(activeCount)} de ${String(list.length)} activos.`}
            </p>
          </div>
          <button
            type="button"
            onClick={() => {
              setEditing({ kind: 'new' });
            }}
            className="rounded-lg bg-sky-600 px-3 py-2 text-sm font-medium text-white hover:bg-sky-500 focus-visible:outline-2 focus-visible:outline-sky-300"
          >
            + Nuevo concepto
          </button>
        </div>

        <div className="overflow-hidden rounded-xl border border-slate-800 bg-slate-900/40">
          {concepts.isPending && <p className="p-4 text-sm text-slate-400">Cargando conceptos…</p>}
          {concepts.error && (
            <p role="alert" className="p-4 text-sm text-rose-300">
              {concepts.error.message}
            </p>
          )}
          {concepts.isSuccess && list.length === 0 && (
            <p className="p-4 text-sm text-slate-400">
              Todavía no hay conceptos. Crea uno o carga los de ejemplo con{' '}
              <code className="font-mono text-slate-300">wsl make seed</code>.
            </p>
          )}
          {list.length > 0 && (
            <ConceptTable
              concepts={list}
              selectedId={selected?.id ?? null}
              togglingId={toggle.isPending ? toggle.variables.id : null}
              onSelect={(concept: Concept) => {
                setEditing({ kind: 'edit', id: concept.id });
              }}
              onToggleActive={(concept: Concept) => {
                toggle.mutate({ id: concept.id, patch: { is_active: !concept.is_active } });
              }}
            />
          )}
        </div>
        {toggle.error && (
          <p role="alert" className="mt-2 text-sm text-rose-300">
            {toggle.error.message}
          </p>
        )}
      </section>

      <aside className="min-w-0">
        {/* Si el concepto que se editaba ya no está (otra persona lo borró),
            se cierra el panel en lugar de mostrar un formulario vacío. */}
        {editing.kind === 'none' || (editing.kind === 'edit' && !selected) ? (
          <div className="rounded-xl border border-dashed border-slate-800 p-6 text-sm text-slate-400">
            Elige un concepto para editarlo o probarlo, o crea uno nuevo.
          </div>
        ) : (
          <ConceptForm
            // La key reinicia el formulario al cambiar de concepto y también
            // cuando el concepto cambia en el servidor (por ejemplo, con el
            // interruptor de la tabla): si no, el formulario mostraría datos
            // viejos y al guardar desharía ese cambio sin avisar.
            key={selected ? `${String(selected.id)}:${selected.updated_at}` : 'nuevo'}
            concept={selected}
            onSaved={(concept) => {
              setEditing({ kind: 'edit', id: concept.id });
            }}
            onClose={close}
          />
        )}
      </aside>
    </div>
  );
}
