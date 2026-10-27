/**
 * Panel lateral del muro: todo lo que se sabe de una entidad (Fase 9.6, H9.3).
 *
 * Entra por la derecha al elegir un nodo:
 * - tipo, nombre y **estatus legal grande** (siempre visible, §9.10);
 * - alias y lo que se le unió;
 * - sus fechas (primera y última nota);
 * - sus vínculos: clic en uno elige a la otra entidad y la cámara vuela;
 * - sus menciones con la cita y la liga a la nota.
 *
 * Una persona se dibuja junto al lugar de sus notas, no en su domicilio: el
 * panel lo dice para no sugerir otra cosa.
 *
 * No hace: no confirma ni edita (eso es la pestaña Casos).
 */
import { useCaseEntities } from '../../hooks/useEntities';
import type { CaseGraph, GraphNode } from '../../services/caseGraph';
import { useExplorerStore } from '../../store/explorer';
import { relationshipPhrase } from '../Cases/labels';
import { formatDay } from './format';
import { GLASS } from './ui';
import { ExternalLink } from '../ExternalLink';

interface WallPanelProps {
  caseId: string;
  node: GraphNode;
  graph: CaseGraph;
  onClose: () => void;
}

export function WallPanel({ caseId, node, graph, onClose }: WallPanelProps) {
  const entity = useCaseEntities(caseId, 'confirmed').data?.items.find((e) => e.id === node.id);
  const links = graph.edges.filter((e) => e.entity_a.id === node.id || e.entity_b.id === node.id);

  return (
    <aside
      aria-label={`Ficha de ${node.label}`}
      className={`${GLASS} absolute inset-x-2 bottom-2 z-20 max-h-[55%] animate-[fadeIn_250ms_ease-out] overflow-y-auto p-4 text-sm text-slate-200 md:inset-x-auto md:bottom-4 md:right-4 md:top-20 md:max-h-none md:w-96`}
    >
      <div className="flex items-start justify-between gap-2">
        <div>
          <p className="text-xs uppercase tracking-wide text-slate-400">{node.type_label}</p>
          <h3 className="text-lg font-semibold text-slate-50">{node.label}</h3>
        </div>
        <button
          type="button"
          onClick={onClose}
          aria-label="Cerrar ficha"
          className="rounded-md px-2 py-1 text-slate-300 hover:bg-slate-800"
        >
          ✕
        </button>
      </div>
      {node.type === 'person' && (
        <p className="mt-2 rounded-lg bg-amber-500/15 px-3 py-2 text-sm font-semibold text-amber-100">
          Estatus legal: {node.legal_status_label ?? 'la nota no lo dice'}
        </p>
      )}
      <p className="mt-2 text-xs text-slate-400">
        {node.mention_count} {node.mention_count === 1 ? 'mención' : 'menciones'} en{' '}
        {node.article_count} {node.article_count === 1 ? 'nota' : 'notas'}
        {node.first_seen && ` · del ${formatDay(node.first_seen)}`}
        {node.last_seen && node.last_seen !== node.first_seen && ` al ${formatDay(node.last_seen)}`}
      </p>
      {!node.pinned && (
        <p className="mt-1 text-xs text-slate-500">
          Ubicada junto al lugar de sus notas (no es un domicilio).
        </p>
      )}
      {entity && entity.aliases.length > 0 && (
        <p className="mt-2 text-xs text-slate-300">También: {entity.aliases.join(', ')}</p>
      )}
      {entity && entity.merged.length > 0 && (
        <p className="mt-1 text-xs text-slate-400">
          Unió a: {entity.merged.map((m) => m.label).join(', ')}
        </p>
      )}

      <h4 className="mt-4 text-xs font-semibold uppercase tracking-wide text-slate-400">
        Vínculos ({links.length})
      </h4>
      {links.length === 0 && (
        <p className="mt-1 text-xs text-slate-500">
          Sin vínculos todavía. Se sugieren al confirmar entidades que salen en las mismas notas.
        </p>
      )}
      <ul className="mt-1 space-y-1">
        {links.map((link) => {
          const other = link.entity_a.id === node.id ? link.entity_b : link.entity_a;
          return (
            <li key={`${String(link.entity_a.id)}-${String(link.entity_b.id)}-${link.type}`}>
              <button
                type="button"
                onClick={() => {
                  useExplorerStore.getState().selectWallNode(other.id);
                }}
                className="w-full rounded-md px-2 py-1 text-left text-xs hover:bg-slate-800"
              >
                <span className="text-slate-400">{relationshipPhrase(link)}</span>{' '}
                <span className="text-slate-100">{other.label}</span>
                {other.legal_status_label && (
                  <span className="text-amber-200"> ({other.legal_status_label})</span>
                )}
                <span className="block text-[11px] text-slate-500">
                  {link.review_status === 'confirmed' ? 'confirmado' : 'sugerido'} ·{' '}
                  {link.origin_label}
                </span>
              </button>
            </li>
          );
        })}
      </ul>

      <h4 className="mt-4 text-xs font-semibold uppercase tracking-wide text-slate-400">
        Menciones
      </h4>
      {!entity && <p className="mt-1 text-xs text-slate-500">Cargando citas…</p>}
      <ul className="mt-1 space-y-2">
        {entity?.mentions.map((m) => (
          <li key={m.id} className="text-xs">
            <blockquote className="text-slate-200">«{m.evidence_span}»</blockquote>
            <ExternalLink href={m.article_url} className="text-sky-300 hover:underline">
              {m.source_name ?? m.article_title} ↗
            </ExternalLink>
            {m.published_at && (
              <span className="text-slate-500"> · {formatDay(m.published_at)}</span>
            )}
          </li>
        ))}
      </ul>
    </aside>
  );
}
