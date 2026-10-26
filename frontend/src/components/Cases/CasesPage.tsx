/**
 * Pantalla "Casos" (Fase 9.3, historia H9.1).
 *
 * A la izquierda, mis casos; a la derecha, el caso abierto (con sus noticias)
 * o el formulario para crear o editar uno. Las noticias se agregan desde
 * Explorar con «Agregar al caso».
 *
 * No hace llamadas HTTP: usa los hooks de `useCases`.
 */
import { useState } from 'react';

import type { Case } from '../../services/cases';
import { CaseDetail } from './CaseDetail';
import { CaseForm } from './CaseForm';
import { CaseList } from './CaseList';

/** Qué muestra el panel derecho. */
type Panel =
  { kind: 'none' } | { kind: 'new' } | { kind: 'open'; id: string } | { kind: 'edit'; item: Case };

export function CasesPage() {
  const [panel, setPanel] = useState<Panel>({ kind: 'none' });
  const selectedId =
    panel.kind === 'open' ? panel.id : panel.kind === 'edit' ? panel.item.id : null;
  const open = (saved: Case) => {
    setPanel({ kind: 'open', id: saved.id });
  };

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto grid max-w-7xl gap-6 px-4 py-6 sm:px-6 lg:grid-cols-[minmax(0,26rem)_minmax(0,1fr)]">
        <section aria-labelledby="casos-titulo" className="min-w-0">
          <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
            <div>
              <h2 id="casos-titulo" className="titulo-oraculo text-base font-bold text-sky-50">
                Casos
              </h2>
              <p className="text-sm text-slate-400">
                Investigaciones con sus noticias. Solo ves los casos de los que eres miembro.
              </p>
            </div>
            <button
              type="button"
              onClick={() => {
                setPanel({ kind: 'new' });
              }}
              className="rounded-lg bg-sky-600 px-3 py-2 text-sm font-medium text-white hover:bg-sky-500 focus-visible:outline-2 focus-visible:outline-sky-300"
            >
              + Nuevo caso
            </button>
          </div>
          <CaseList
            selectedId={selectedId}
            onSelect={(id) => {
              setPanel({ kind: 'open', id });
            }}
          />
        </section>
        <div className="min-w-0">
          {panel.kind === 'none' && (
            <p className="rounded-xl border border-dashed border-slate-800 p-6 text-sm text-slate-400">
              Elige un caso para ver sus noticias, o crea uno nuevo.
            </p>
          )}
          {panel.kind === 'new' && (
            <CaseForm
              onSaved={open}
              onCancel={() => {
                setPanel({ kind: 'none' });
              }}
            />
          )}
          {panel.kind === 'edit' && (
            <CaseForm
              key={panel.item.id}
              editing={panel.item}
              onSaved={open}
              onCancel={() => {
                setPanel({ kind: 'open', id: panel.item.id });
              }}
            />
          )}
          {panel.kind === 'open' && (
            <CaseDetail
              key={panel.id}
              caseId={panel.id}
              onEdit={(item) => {
                setPanel({ kind: 'edit', item });
              }}
            />
          )}
        </div>
      </div>
    </div>
  );
}
