/**
 * Pestaña «Noticias» del detalle de un caso (Fase 9.3; separada en F12).
 *
 * Cada noticia con su medio, fecha y lugar, «Ver nota original» y, si el caso
 * está abierto y quien mira puede editar, «Quitar». Antes vivía dentro de
 * `CaseDetail`; se separó cuando el detalle pasó a tener pestañas.
 *
 * No hace: no agrega notas (eso es el botón «Agregar al caso» de Explorar).
 */
import { useCaseArticles, useRemoveCaseArticle } from '../../hooks/useCases';
import { formatDay, PRECISION_LABEL } from '../Explore/format';
import { ExternalLink } from '../ExternalLink';
import { HudButton } from '../ui/HudButton';

interface CaseArticlesProps {
  caseId: string;
  articleCount: number;
  /** Puede quitar notas: editor o dueño, con el caso abierto. */
  canEdit: boolean;
}

export function CaseArticles({ caseId, articleCount, canEdit }: CaseArticlesProps) {
  const articles = useCaseArticles(caseId);
  const remove = useRemoveCaseArticle();

  return (
    <div className="hud-panel hud-reveal overflow-hidden">
      <div className="hud-section-head">
        <h3 className="hud-section-title">Noticias del caso ({articleCount})</h3>
      </div>
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
                {canEdit && (
                  <HudButton
                    variant="danger"
                    size="sm"
                    disabled={remove.isPending}
                    onClick={() => {
                      remove.mutate({ caseId, articleId: article.article_id });
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
    </div>
  );
}
