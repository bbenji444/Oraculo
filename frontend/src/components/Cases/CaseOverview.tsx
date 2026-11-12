/**
 * Pestaña «Panorama» del detalle de un caso (F12, ADR-0107).
 *
 * Benji pidió que las relaciones del caso **sirvan para algo**. El Panorama
 * responde de un vistazo «¿quién está en este caso y con quién se relaciona?»:
 *
 * - Lo confirmado, agrupado por tipo (Personas primero, por estatus legal).
 * - En cada entidad, sus conexiones útiles (`connectionsOf`): los vínculos
 *   confirmados y los sugeridos fuertes, cada uno con **por qué** («participan
 *   en el mismo hecho en 2 notas»). Lo sugerido dice «por revisar».
 * - Arriba, cuánto falta revisar, con un clic a la pestaña donde se hace.
 *
 * Solo lee: confirmar, descartar o dibujar vínculos se hace en Entidades y
 * Vínculos. No hace: no muestra lo descartado ni los vínculos débiles sin
 * confirmar (siguen en Vínculos, D4).
 */
import { useCaseEntities } from '../../hooks/useEntities';
import { useCaseRelationships } from '../../hooks/useRelationships';
import type { Entity } from '../../services/entities';
import type { RelationshipEnd } from '../../services/relationships';
import { type Connection, connectionsOf, groupByType, participatesInEvent } from './grouping';
import { countLabel, selectionSummary } from './selection';

// Más de cinco conexiones por tarjeta ya no se lee de un vistazo; el resto
// está a un clic en Vínculos.
const MAX_CONNECTIONS = 5;

interface CaseOverviewProps {
  caseId: string;
  canEdit: boolean;
  /** Lleva a la pestaña donde se revisa. */
  onNavigate: (section: 'entities' | 'relationships') => void;
}

export function CaseOverview({ caseId, canEdit, onNavigate }: CaseOverviewProps) {
  const entities = useCaseEntities(caseId, 'confirmed');
  const confirmedLinks = useCaseRelationships(caseId, 'confirmed');
  const suggestedLinks = useCaseRelationships(caseId, 'suggested');
  const confirmed = entities.data?.items ?? [];
  const links = [...(confirmedLinks.data?.items ?? []), ...(suggestedLinks.data?.items ?? [])];
  const pendingEntities = entities.data?.counts.suggested ?? 0;
  const pendingLinks = suggestedLinks.data?.counts.suggested ?? 0;
  const strongPending = (suggestedLinks.data?.items ?? []).filter(
    (r) => r.strength === 'strong',
  ).length;
  const error = entities.error ?? confirmedLinks.error ?? suggestedLinks.error;
  const groups = groupByType(confirmed);

  return (
    <div className="hud-panel hud-spot hud-reveal overflow-hidden">
      <div className="hud-section-head">
        <h3 className="hud-section-title">Panorama</h3>
        {confirmed.length > 0 && (
          <p className="text-xs text-slate-400">
            Confirmado: {selectionSummary(groups.flatMap((g) => g.items))}
          </p>
        )}
      </div>
      {canEdit && (pendingEntities > 0 || pendingLinks > 0) && (
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 border-b border-amber-300/20 bg-amber-300/[0.04] px-5 py-2.5 text-xs text-amber-100">
          <span>Por revisar:</span>
          {pendingEntities > 0 && (
            <button
              type="button"
              onClick={() => {
                onNavigate('entities');
              }}
              className="text-sky-300 underline-offset-2 hover:underline"
            >
              {countLabel(pendingEntities, 'entidad', 'entidades')}
            </button>
          )}
          {pendingLinks > 0 && (
            <button
              type="button"
              onClick={() => {
                onNavigate('relationships');
              }}
              className="text-sky-300 underline-offset-2 hover:underline"
            >
              {countLabel(pendingLinks, 'vínculo', 'vínculos')}
              {strongPending > 0 && ` (${String(strongPending)} fuertes)`}
            </button>
          )}
        </div>
      )}
      {error && (
        <p role="alert" className="px-4 pt-2 text-xs text-rose-300">
          {error.message}
        </p>
      )}
      {entities.isPending && <p className="p-4 text-sm text-slate-400">Armando el panorama…</p>}
      {entities.isSuccess && confirmed.length === 0 && (
        <div className="space-y-2 p-5 text-sm text-slate-400">
          <p>
            Todavía no hay nada confirmado. Cuando confirmes las personas, organizaciones y
            vehículos que sirvan, aquí verás quién se relaciona con quién y por qué.
          </p>
          {pendingEntities > 0 && (
            <button
              type="button"
              onClick={() => {
                onNavigate('entities');
              }}
              className="hud-btn hud-btn--solid hud-btn--sm"
            >
              Revisar {countLabel(pendingEntities, 'entidad', 'entidades')}
            </button>
          )}
        </div>
      )}
      {groups.map((group) => (
        <section
          key={group.type}
          aria-label={group.label}
          className="border-b border-sky-400/10 last:border-b-0"
        >
          <h4 className="bg-sky-400/[0.02] px-5 py-2 font-display text-[11px] tracking-[0.16em] text-sky-100 uppercase">
            {group.label} · {group.items.length}
          </h4>
          <ul className="grid gap-2 p-3 sm:grid-cols-2">
            {group.items.map((entity) => (
              <OverviewEntity
                key={entity.id}
                entity={entity}
                connections={connectionsOf(entity.id, links)}
                onMore={() => {
                  onNavigate('relationships');
                }}
              />
            ))}
          </ul>
        </section>
      ))}
    </div>
  );
}

function Name({ end }: { end: Pick<RelationshipEnd, 'label' | 'legal_status_label'> }) {
  return (
    <>
      <span className="text-slate-100">{end.label}</span>
      {end.legal_status_label && (
        <span className="ml-1 text-[11px] font-medium text-amber-200">
          ({end.legal_status_label})
        </span>
      )}
    </>
  );
}

/** Por qué se relacionan; si una persona dijo cómo («familiar»), va primero. */
function connectionText({ relationship }: Connection): string {
  if (relationship.type === 'appears_with') return relationship.reason;
  const how = relationship.custom_label ?? relationship.type_label;
  return `${how} · ${relationship.reason}`;
}

function OverviewEntity({
  entity,
  connections,
  onMore,
}: {
  entity: Entity;
  connections: Connection[];
  onMore: () => void;
}) {
  const rest = connections.length - MAX_CONNECTIONS;
  return (
    <li className="rounded-lg border border-sky-400/15 bg-sky-400/[0.02] p-3">
      <p className="text-sm">
        <Name end={entity} />
      </p>
      <p className="mt-0.5 text-xs text-slate-400">
        {countLabel(entity.article_count, 'nota', 'notas')}
        {participatesInEvent(entity) && ' · participa en el hecho'}
      </p>
      {connections.length === 0 ? (
        <p className="mt-2 text-xs text-slate-500">Sin relaciones fuertes todavía.</p>
      ) : (
        <ul
          aria-label={`Con quién se relaciona ${entity.label}`}
          className="mt-2 space-y-1 text-xs"
        >
          {connections.slice(0, MAX_CONNECTIONS).map((c) => (
            <li key={`${String(c.other.id)}-${c.relationship.type}`}>
              <span aria-hidden="true" className="mr-1 text-sky-300">
                ↔
              </span>
              <Name end={c.other} />
              <span className={c.pending ? 'text-slate-400' : 'text-emerald-200'}>
                : {connectionText(c)}
              </span>
              {c.pending && <span className="ml-1 text-amber-200">(por revisar)</span>}
            </li>
          ))}
          {rest > 0 && (
            <li>
              <button
                type="button"
                onClick={onMore}
                className="text-sky-300 underline-offset-2 hover:underline"
              >
                y {rest} más en Vínculos
              </button>
            </li>
          )}
        </ul>
      )}
    </li>
  );
}
