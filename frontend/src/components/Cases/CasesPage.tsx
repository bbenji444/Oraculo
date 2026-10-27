/**
 * Pantalla "Casos" (Fase 9.3, historia H9.1).
 *
 * A la izquierda, mis casos; a la derecha, el caso abierto (con sus noticias)
 * o el formulario para crear o editar uno. Las noticias se agregan desde
 * Explorar con «Agregar al caso».
 *
 * El dueño puede eliminar un caso; al hacerlo sale «Deshacer» (27/10/2026).
 *
 * Diseño «consola táctica» (ADR-0036).
 *
 * No hace llamadas HTTP: usa los hooks de `useCases`.
 */
import { useCallback, useState } from 'react';

import { useRestoreCase } from '../../hooks/useCases';
import type { Case } from '../../services/cases';
import { CaseDetail } from './CaseDetail';
import { CaseForm } from './CaseForm';
import { CaseList } from './CaseList';
import { UndoToast } from '../UndoToast';
import { HudButton } from '../ui/HudButton';
import { SectionHeading } from '../ui/SectionHeading';

/** Qué muestra el panel derecho. */
type Panel =
  { kind: 'none' } | { kind: 'new' } | { kind: 'open'; id: string } | { kind: 'edit'; item: Case };

export function CasesPage() {
  const [panel, setPanel] = useState<Panel>({ kind: 'none' });
  // El último caso eliminado, para «Deshacer» (27/10/2026).
  const [removed, setRemoved] = useState<Case | null>(null);
  const restore = useRestoreCase();
  const closeUndo = useCallback(() => {
    setRemoved(null);
  }, []);
  const selectedId =
    panel.kind === 'open' ? panel.id : panel.kind === 'edit' ? panel.item.id : null;
  const open = (saved: Case) => {
    setPanel({ kind: 'open', id: saved.id });
  };

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto grid max-w-7xl gap-6 px-4 py-6 sm:px-6 lg:grid-cols-[minmax(0,26rem)_minmax(0,1fr)]">
        <section aria-labelledby="casos-titulo" className="min-w-0">
          <div id="casos-titulo" className="mb-6">
            <SectionHeading
              kicker="Expedientes de investigación"
              title="Casos"
              description="Investigaciones con sus noticias. Solo ves los casos de los que eres miembro."
              actions={
                <HudButton
                  variant="solid"
                  onClick={() => {
                    setPanel({ kind: 'new' });
                  }}
                >
                  + Nuevo caso
                </HudButton>
              }
            />
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
            <p className="hud-empty">Elige un caso para ver sus noticias, o crea uno nuevo.</p>
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
              onDeleted={(item) => {
                setPanel({ kind: 'none' });
                setRemoved(item);
              }}
            />
          )}
        </div>
      </div>
      {removed && (
        <UndoToast
          message={`Se eliminó el caso «${removed.name}».`}
          busy={restore.isPending}
          onUndo={() => {
            restore.mutate(removed.id, {
              onSuccess: (back) => {
                setRemoved(null);
                setPanel({ kind: 'open', id: back.id });
              },
            });
          }}
          onClose={closeUndo}
        />
      )}
    </div>
  );
}
