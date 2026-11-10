/**
 * Pantalla "Conceptos" (especificación §14.1, historia H2).
 *
 * A la izquierda la tabla de conceptos; a la derecha el formulario para
 * crear o editar, con "Probar concepto" debajo. Los datos llegan por los
 * hooks de TanStack Query; esta pantalla no hace llamadas HTTP.
 *
 * Diseño «consola táctica» (ADR-0036): encabezado que se descifra, tabla en un
 * panel con borde de luz y formulario a la derecha.
 *
 * Debajo de la tabla, las subdivisiones (02/11/2026, ADR-0038): todas, también
 * las apagadas. Cada una se edita a la derecha con las palabras de su tema
 * general; por eso los temas no se repiten en la tabla de conceptos.
 */
import { useState } from 'react';

import { useCategories } from '../../hooks/useCategories';
import { useConcepts, useUpdateConcept } from '../../hooks/useConcepts';
import type { Concept } from '../../services/concepts';
import { ConceptForm } from './ConceptForm';
import { ConceptTable } from './ConceptTable';
import { SubdivisionForm } from './SubdivisionForm';
import { SubdivisionList } from './SubdivisionList';
import { HudButton } from '../ui/HudButton';
import { HudPanel } from '../ui/HudPanel';
import { SectionHeading } from '../ui/SectionHeading';

/** Qué muestra el panel derecho: nada, un concepto (nuevo o existente) o una subdivisión. */
type Editing =
  | { kind: 'none' }
  | { kind: 'new' }
  | { kind: 'edit'; id: number }
  | { kind: 'subdivision'; id: number }
  | { kind: 'new-subdivision' };

export function ConceptsPage() {
  const concepts = useConcepts();
  const categories = useCategories(true);
  const toggle = useUpdateConcept();
  const [editing, setEditing] = useState<Editing>({ kind: 'none' });
  const all = concepts.data ?? [];
  // Los temas generales se editan con su subdivisión, abajo.
  const list = all.filter((c) => c.category_id === null);
  const selected = editing.kind === 'edit' ? all.find((c) => c.id === editing.id) : undefined;
  const activeCount = list.filter((c) => c.is_active).length;
  const subdivision =
    editing.kind === 'subdivision' ? categories.data?.find((c) => c.id === editing.id) : undefined;
  const topicId = subdivision?.topic_concept_id ?? null;
  const topic = topicId === null ? undefined : all.find((c) => c.id === topicId);

  function close() {
    setEditing({ kind: 'none' });
  }

  return (
    <div className="mx-auto grid max-w-7xl gap-6 px-4 py-6 sm:px-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,32rem)]">
      <section aria-labelledby="conceptos-titulo" className="min-w-0">
        <div id="conceptos-titulo" className="mb-6">
          <SectionHeading
            kicker="Plantillas de búsqueda"
            title="Conceptos"
            description={`Palabras clave, exclusiones y color.${
              concepts.isSuccess ? ` ${String(activeCount)} de ${String(list.length)} activos.` : ''
            }`}
            actions={
              <HudButton
                variant="solid"
                onClick={() => {
                  setEditing({ kind: 'new' });
                }}
              >
                + Nuevo concepto
              </HudButton>
            }
          />
        </div>

        <HudPanel className="overflow-hidden p-1.5">
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
        </HudPanel>
        {toggle.error && (
          <p role="alert" className="mt-2 text-sm text-rose-300">
            {toggle.error.message}
          </p>
        )}

        <div id="subdivisiones" className="mt-8 mb-4">
          <SectionHeading
            kicker="Fiscalía General de la República"
            title="Subdivisiones"
            description="Con ellas la IA clasifica cada nota y, con las palabras de su tema, se buscan solas o junto con la FGR."
            actions={
              <HudButton
                onClick={() => {
                  setEditing({ kind: 'new-subdivision' });
                }}
              >
                + Nueva subdivisión
              </HudButton>
            }
          />
        </div>
        <HudPanel className="overflow-hidden">
          {categories.isPending && (
            <p className="p-4 text-sm text-slate-400">Cargando subdivisiones…</p>
          )}
          {categories.error && (
            <p role="alert" className="p-4 text-sm text-rose-300">
              {categories.error.message}
            </p>
          )}
          {categories.data && (
            <SubdivisionList
              categories={categories.data}
              selectedId={subdivision?.id ?? null}
              onSelect={(category) => {
                setEditing({ kind: 'subdivision', id: category.id });
              }}
            />
          )}
        </HudPanel>
      </section>

      <aside className="min-w-0">
        {/* Si el concepto que se editaba ya no está (otra persona lo borró),
            se cierra el panel en lugar de mostrar un formulario vacío. */}
        {editing.kind === 'new-subdivision' ? (
          <SubdivisionForm
            key="nueva"
            topic={undefined}
            onClose={close}
            onCreated={(created) => {
              setEditing({ kind: 'subdivision', id: created.id });
            }}
          />
        ) : editing.kind === 'subdivision' && subdivision ? (
          <SubdivisionForm
            // Otra subdivisión: el formulario arranca con lo guardado.
            key={subdivision.id}
            category={subdivision}
            topic={topic}
            onClose={close}
          />
        ) : editing.kind === 'none' ||
          editing.kind === 'subdivision' ||
          (editing.kind === 'edit' && !selected) ? (
          <div className="hud-empty">
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
