/**
 * Detalle de un caso (Fase 9.3): sus datos, cerrar, archivar o reabrir, y sus
 * noticias, cada una con "Ver nota original" y "Quitar del caso".
 *
 * Abrirlo queda en la bitácora del servidor (`case.viewed`). Un caso cerrado
 * o archivado es de solo lectura: no ofrece editar ni quitar notas. Un lector
 * tampoco.
 *
 * Debajo, la sección Entidades (9.4): lo que la IA propone de sus notas para
 * confirmar o descartar. El muro sobre el globo llega en la 9.6.
 *
 * No hace: no agrega notas (eso es el botón "Agregar al caso" de Explorar).
 */
import {
  useCase,
  useCaseArticles,
  useRemoveCaseArticle,
  useUpdateCase,
} from '../../hooks/useCases';
import type { Case, CaseStatus } from '../../services/cases';
import { formatDay, PRECISION_LABEL } from '../Explore/format';
import { CaseEntities } from './CaseEntities';
import { SENSITIVITY_TONE, STATUS_TONE } from './labels';

interface CaseDetailProps {
  caseId: string;
  onEdit: (item: Case) => void;
}

const ACTION_BUTTON =
  'rounded-lg border border-slate-700 px-3 py-1.5 text-xs text-slate-200 hover:bg-slate-800 focus-visible:outline-2 focus-visible:outline-sky-400 disabled:opacity-50';

export function CaseDetail({ caseId, onEdit }: CaseDetailProps) {
  const detail = useCase(caseId);
  const articles = useCaseArticles(caseId);
  const update = useUpdateCase();
  const remove = useRemoveCaseArticle();

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
      <div className="space-y-3 rounded-xl border border-slate-800 bg-slate-900/60 p-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <h2 className="text-lg font-semibold text-slate-50">{item.name}</h2>
            <p className="mt-1 flex flex-wrap items-center gap-2 text-xs">
              <span className={`rounded-md px-1.5 py-0.5 ${STATUS_TONE[item.status]}`}>
                {item.status_label}
              </span>
              <span className={`rounded-md px-1.5 py-0.5 ${SENSITIVITY_TONE[item.sensitivity]}`}>
                {item.sensitivity_label}
              </span>
              <span className="text-slate-400">
                Creado por {item.created_by} el {formatDay(item.created_at)}
              </span>
            </p>
          </div>
          {canEdit && (
            <div className="flex flex-wrap gap-2">
              {isOpen && (
                <>
                  <button
                    type="button"
                    className={ACTION_BUTTON}
                    onClick={() => {
                      onEdit(item);
                    }}
                  >
                    Editar
                  </button>
                  <button
                    type="button"
                    className={ACTION_BUTTON}
                    disabled={update.isPending}
                    onClick={() => {
                      setStatus('closed');
                    }}
                  >
                    Cerrar caso
                  </button>
                </>
              )}
              {item.status === 'closed' && (
                <button
                  type="button"
                  className={ACTION_BUTTON}
                  disabled={update.isPending}
                  onClick={() => {
                    setStatus('archived');
                  }}
                >
                  Archivar
                </button>
              )}
              {!isOpen && (
                <button
                  type="button"
                  className={ACTION_BUTTON}
                  disabled={update.isPending}
                  onClick={() => {
                    setStatus('open');
                  }}
                >
                  Reabrir
                </button>
              )}
            </div>
          )}
        </div>
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
      </div>

      <div className="rounded-xl border border-slate-800 bg-slate-900/40">
        <h3 className="border-b border-slate-800 px-4 py-3 text-sm font-semibold text-slate-100">
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
        <ul className="divide-y divide-slate-800">
          {articles.data?.map((article) => {
            const location = article.primary_location;
            return (
              <li key={article.article_id} className="flex flex-wrap items-start gap-3 px-4 py-3">
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
                  <a
                    href={article.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="rounded-lg bg-sky-500/20 px-2.5 py-1 text-xs font-medium text-sky-100 hover:bg-sky-500/30 focus-visible:outline-2 focus-visible:outline-sky-400"
                  >
                    Ver nota original ↗
                  </a>
                  {canEdit && isOpen && (
                    <button
                      type="button"
                      disabled={remove.isPending}
                      onClick={() => {
                        remove.mutate({ caseId: item.id, articleId: article.article_id });
                      }}
                      className="rounded-lg px-2.5 py-1 text-xs text-rose-300 hover:bg-rose-500/10 focus-visible:outline-2 focus-visible:outline-rose-400 disabled:opacity-50"
                    >
                      Quitar
                    </button>
                  )}
                </div>
              </li>
            );
          })}
        </ul>
      </div>

      <CaseEntities caseId={item.id} canEdit={canEdit && isOpen} />
    </section>
  );
}
