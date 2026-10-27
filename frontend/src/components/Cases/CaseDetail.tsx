/**
 * Detalle de un caso (Fase 9.3): sus datos, cerrar, archivar o reabrir, y sus
 * noticias, cada una con "Ver nota original" y "Quitar del caso".
 *
 * Abrirlo queda en la bitácora del servidor (`case.viewed`). Un caso cerrado
 * o archivado es de solo lectura: no ofrece editar ni quitar notas. Un lector
 * tampoco.
 *
 * Debajo, la sección Entidades (9.4): lo que la IA propone de sus notas para
 * confirmar o descartar, con sus posibles duplicados, y la sección Vínculos
 * (9.5). El muro sobre el globo llega en la 9.6.
 *
 * El dueño puede eliminar el caso (27/10/2026): pide confirmación y es
 * reversible (`CasesPage` ofrece «Deshacer»).
 *
 * Diseño «consola táctica» (ADR-0036): cabecera en un panel con borde de luz,
 * insignias con pulso y cada noticia como una fila que se ilumina.
 *
 * No hace: no agrega notas (eso es el botón "Agregar al caso" de Explorar).
 */
import type { CSSProperties } from 'react';

import {
  useCase,
  useCaseArticles,
  useDeleteCase,
  useRemoveCaseArticle,
  useUpdateCase,
} from '../../hooks/useCases';
import type { Case, CaseStatus } from '../../services/cases';
import { formatDay, PRECISION_LABEL } from '../Explore/format';
import { wallHash } from '../../map/muro/orbit';
import { CaseEntities } from './CaseEntities';
import { CaseRelationships } from './CaseRelationships';
import { SENSITIVITY_TONE, STATUS_TONE } from './labels';
import { ConfirmDelete } from '../ConfirmDelete';
import { ExternalLink } from '../ExternalLink';
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
  const articles = useCaseArticles(caseId);
  const update = useUpdateCase();
  const remove = useRemoveCaseArticle();
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

      <HudPanel className="hud-reveal overflow-hidden" style={{ '--i': 1 } as CSSProperties}>
        <h3 className="border-b border-sky-400/10 px-5 py-3 font-display text-[11px] tracking-[0.2em] text-sky-100 uppercase">
          Noticias del caso ({item.article_count})
        </h3>
        {articles.isPending && <p className="p-4 text-sm text-slate-400">Cargando noticias…</p>}
        {articles.error && (
          <p role="alert" className="p-4 text-sm text-rose-300">
            {articles.error.message}
          </p>
        )}
        {articles.isSuccess && articles.data.length === 0 && (
          <p className="p-4 text-sm text-slate-400">
            Todavía no tiene noticias. En{' '}
            <a href="#/explorar" className="text-sky-300 underline">
              Explorar
            </a>
            , abre una noticia y presiona «Agregar al caso».
          </p>
        )}
        {remove.error && (
          <p role="alert" className="px-4 pt-3 text-xs text-rose-300">
            {remove.error.message}
          </p>
        )}
        <ul className="p-2">
          {articles.data?.map((article) => {
            const location = article.primary_location;
            return (
              <li key={article.article_id} className="hud-row flex-wrap cursor-default items-start">
                <div className="min-w-0 flex-1">
                  <p className="text-sm text-slate-100">{article.title}</p>
                  <p className="mt-0.5 text-xs text-slate-400">
                    {article.source_name ?? article.source_domain ?? 'Medio sin nombre'}
                    {article.published_at && ` · ${formatDay(article.published_at)}`}
                    {' · '}
                    {location?.place ?? PRECISION_LABEL.unknown}
                  </p>
                </div>
                <div className="flex shrink-0 gap-2">
                  <ExternalLink href={article.url} className="hud-btn hud-btn--sm">
                    Ver nota original ↗
                  </ExternalLink>
                  {canEdit && isOpen && (
                    <HudButton
                      variant="danger"
                      size="sm"
                      disabled={remove.isPending}
                      onClick={() => {
                        remove.mutate({ caseId: item.id, articleId: article.article_id });
                      }}
                    >
                      Quitar
                    </HudButton>
                  )}
                </div>
              </li>
            );
          })}
        </ul>
      </HudPanel>

      <CaseEntities caseId={item.id} canEdit={canEdit && isOpen} />
      <CaseRelationships caseId={item.id} canEdit={canEdit && isOpen} />
    </section>
  );
}
