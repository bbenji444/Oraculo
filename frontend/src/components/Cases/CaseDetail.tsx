/**
 * Detalle de un caso (Fase 9.3): sus datos, cerrar, archivar o reabrir, y sus
 * noticias, cada una con "Ver nota original" y "Quitar del caso".
 *
 * Abrirlo queda en la bitácora del servidor (`case.viewed`). Un caso cerrado
 * o archivado es de solo lectura: no ofrece editar ni quitar notas. Un lector
 * tampoco.
 *
 * Debajo, desde F12 (ADR-0107), el caso se divide en pestañas
 * (`CaseSections`): Entidades (9.4, lo que la IA propone de sus notas, con
 * sus posibles duplicados), Vínculos (9.5) y Noticias. Cada pestaña dice
 * cuánto queda por revisar. El muro sobre el globo es la 9.6.
 *
 * El dueño puede eliminar el caso (27/10/2026): pide confirmación y es
 * reversible (`CasesPage` ofrece «Deshacer»).
 *
 * Diseño «consola táctica» (ADR-0036): cabecera en un panel con borde de luz,
 * insignias con pulso y cada noticia como una fila que se ilumina.
 *
 * No hace: no agrega notas (eso es el botón "Agregar al caso" de Explorar).
 */
import { useCase, useDeleteCase, useUpdateCase } from '../../hooks/useCases';
import type { Case, CaseStatus } from '../../services/cases';
import { formatDay } from '../Explore/format';
import { wallHash } from '../../map/muro/orbit';
import { CaseSections } from './CaseSections';
import { SENSITIVITY_TONE, STATUS_TONE } from './labels';
import { ConfirmDelete } from '../ConfirmDelete';
import { DecodeText } from '../ui/DecodeText';
import { HudButton } from '../ui/HudButton';
import { HudChip } from '../ui/HudChip';
import { HudPanel } from '../ui/HudPanel';

interface CaseDetailProps {
  caseId: string;
  onEdit: (item: Case) => void;
  /** Ya se eliminó: quien lo muestra cierra el panel y ofrece deshacer. */
  onDeleted?: (item: Case) => void;
}

export function CaseDetail({ caseId, onEdit, onDeleted }: CaseDetailProps) {
  const detail = useCase(caseId);
  const update = useUpdateCase();
  const deleteCase = useDeleteCase();

  if (detail.isPending) return <p className="text-sm text-slate-400">Abriendo el caso…</p>;
  if (detail.isError) {
    return (
      <p role="alert" className="text-sm text-rose-300">
        {detail.error.message}
      </p>
    );
  }
  const item = detail.data;

  const canEdit = item.role === 'owner' || item.role === 'editor';
  const isOpen = item.status === 'open';
  const setStatus = (status: CaseStatus) => {
    update.mutate({ id: item.id, patch: { status } });
  };

  return (
    <section aria-label={`Caso ${item.name}`} className="space-y-4">
      <HudPanel scan className="hud-reveal space-y-4 p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <p className="hud-kicker">Expediente</p>
            <h2 className="mt-2 font-display text-xl tracking-[0.1em] text-slate-50 uppercase">
              <DecodeText text={item.name} />
            </h2>
            <p className="mt-2 flex flex-wrap items-center gap-2 text-xs">
              <HudChip tone={STATUS_TONE[item.status]} dot live={item.status === 'open'}>
                {item.status_label}
              </HudChip>
              <HudChip tone={SENSITIVITY_TONE[item.sensitivity]}>{item.sensitivity_label}</HudChip>
              <span className="text-slate-400">
                Creado por {item.created_by} el {formatDay(item.created_at)}
              </span>
            </p>
          </div>
          {/* Cualquier miembro puede ver el muro (9.6); abrirlo queda en la bitácora. */}
          <a href={wallHash(item.id)} className="hud-btn hud-btn--solid">
            <span>🌐 Ver en el globo</span>
          </a>
          {canEdit && (
            <div className="flex flex-wrap gap-2">
              {isOpen && (
                <>
                  <HudButton
                    size="sm"
                    onClick={() => {
                      onEdit(item);
                    }}
                  >
                    Editar
                  </HudButton>
                  <HudButton
                    size="sm"
                    disabled={update.isPending}
                    onClick={() => {
                      setStatus('closed');
                    }}
                  >
                    Cerrar caso
                  </HudButton>
                </>
              )}
              {item.status === 'closed' && (
                <HudButton
                  size="sm"
                  disabled={update.isPending}
                  onClick={() => {
                    setStatus('archived');
                  }}
                >
                  Archivar
                </HudButton>
              )}
              {!isOpen && (
                <HudButton
                  size="sm"
                  disabled={update.isPending}
                  onClick={() => {
                    setStatus('open');
                  }}
                >
                  Reabrir
                </HudButton>
              )}
            </div>
          )}
          {/* Solo el dueño: eliminar se lleva el caso para todos sus miembros. */}
          {item.role === 'owner' && (
            <ConfirmDelete
              what="el caso"
              label="Eliminar caso"
              busy={deleteCase.isPending}
              onConfirm={() => {
                deleteCase.mutate(item.id, {
                  onSuccess: () => {
                    onDeleted?.(item);
                  },
                });
              }}
            />
          )}
        </div>
        {deleteCase.error && (
          <p role="alert" className="text-xs text-rose-300">
            {deleteCase.error.message}
          </p>
        )}
        {item.description && (
          <p className="whitespace-pre-line text-sm text-slate-300">{item.description}</p>
        )}
        {!isOpen && (
          <p className="text-xs text-slate-400">
            Caso {item.status_label}: es de solo lectura hasta que se reabra.
          </p>
        )}
        {update.error && (
          <p role="alert" className="text-xs text-rose-300">
            {update.error.message}
          </p>
        )}
      </HudPanel>

      <CaseSections
        caseId={item.id}
        articleCount={item.article_count}
        canEdit={canEdit && isOpen}
      />
    </section>
  );
}
