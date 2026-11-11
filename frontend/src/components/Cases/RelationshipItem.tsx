/**
 * Un vínculo del caso en un renglón (Fase 9.5; separado y ampliado en F12).
 *
 * Se lee en una línea («Julián N — aparecen juntas — Ramón Salas»), con el
 * estatus legal de las personas siempre visible. Debajo, **por qué** se
 * relacionan («participan en el mismo hecho en 2 notas», ADR-0107), su origen
 * y su confianza; al desplegar las notas en común, cada una dice si en ella
 * las dos participan en el hecho.
 *
 * Desde F12 lleva una casilla para elegirlo y revisarlo en bloque.
 *
 * No hace: no pide datos ni decide (avisa con `onReview` y `onSelect`).
 */
import { useState } from 'react';

import type { Relationship, RelationshipEnd } from '../../services/relationships';
import { formatDay } from '../Explore/format';
import { confidencePercent, relationshipPhrase } from './labels';
import { SelectBox } from './SelectBox';
import { ExternalLink } from '../ExternalLink';

// Botones chicos de la consola táctica (ADR-0036): confirmar en verde, descartar en rojo.
const BUTTON = 'hud-btn hud-btn--sm';

function End({ end }: { end: RelationshipEnd }) {
  return (
    <span className="text-slate-100">
      {end.label}
      {end.legal_status_label && (
        <span className="ml-1 text-[11px] font-medium text-amber-200">
          ({end.legal_status_label})
        </span>
      )}
    </span>
  );
}

interface RelationshipItemProps {
  relationship: Relationship;
  canEdit: boolean;
  busy: boolean;
  onReview: (action: 'confirm' | 'discard') => void;
  /** Si está elegido para revisar en bloque (F12). */
  selected: boolean;
  onSelect: (checked: boolean) => void;
}

export function RelationshipItem({
  relationship,
  canEdit,
  busy,
  onReview,
  selected,
  onSelect,
}: RelationshipItemProps) {
  const [open, setOpen] = useState(false);
  const notes = relationship.shared_articles.length;
  const strong = relationship.strength === 'strong';

  return (
    <li
      className={`hud-reveal px-5 py-3.5 transition-colors duration-300 hover:bg-sky-400/[0.03] ${
        selected ? 'bg-sky-400/[0.05]' : ''
      }`}
    >
      <div className="flex flex-wrap items-start gap-3">
        {canEdit && (
          <span className="pt-0.5">
            <SelectBox
              state={selected ? 'all' : 'none'}
              label={`Elegir ${relationship.entity_a.label} y ${relationship.entity_b.label}`}
              disabled={busy}
              onChange={onSelect}
            />
          </span>
        )}
        <div className="min-w-0 flex-1 text-sm">
          <p>
            <End end={relationship.entity_a} />
            <span className="mx-2 text-slate-400">{relationshipPhrase(relationship)}</span>
            <End end={relationship.entity_b} />
          </p>
          <p className={`mt-1 text-xs ${strong ? 'text-emerald-200' : 'text-slate-300'}`}>
            Por qué: {relationship.reason}
          </p>
          <p className="mt-0.5 text-xs text-slate-400">
            {relationship.origin_label} · confianza {confidencePercent(relationship.confidence)}
            {notes > 0 && (
              <>
                {' · '}
                <button
                  type="button"
                  aria-expanded={open}
                  onClick={() => {
                    setOpen(!open);
                  }}
                  className="text-sky-300 underline-offset-2 hover:underline"
                >
                  {notes === 1 ? 'ver la nota en común' : `ver las ${String(notes)} notas en común`}
                </button>
              </>
            )}
            {relationship.reviewed_by &&
              ` · ${relationship.review_status_label} por ${relationship.reviewed_by}${
                relationship.reviewed_at ? ` el ${formatDay(relationship.reviewed_at)}` : ''
              }`}
          </p>
          {relationship.notes && (
            <p className="mt-1 text-xs text-slate-300">Nota: {relationship.notes}</p>
          )}
        </div>
        {canEdit && (
          <div className="flex shrink-0 gap-2">
            {relationship.review_status !== 'confirmed' && (
              <button
                type="button"
                disabled={busy}
                onClick={() => {
                  onReview('confirm');
                }}
                className={`${BUTTON} border-emerald-400/50 text-emerald-100`}
              >
                Confirmar
              </button>
            )}
            {relationship.review_status !== 'discarded' && (
              <button
                type="button"
                disabled={busy}
                onClick={() => {
                  onReview('discard');
                }}
                className={`${BUTTON} hud-btn--danger`}
              >
                Descartar
              </button>
            )}
          </div>
        )}
      </div>
      {open && (
        <ul className="mt-2 space-y-1 border-l-2 border-sky-400/30 pl-3 text-xs">
          {relationship.shared_articles.map((a) => (
            <li key={a.article_id}>
              <ExternalLink href={a.url} className="text-sky-300 hover:underline">
                {a.title} ↗
              </ExternalLink>
              {a.published_at && (
                <span className="text-slate-400"> · {formatDay(a.published_at)}</span>
              )}
              <span className={a.same_event ? 'text-emerald-200' : 'text-slate-500'}>
                {a.same_event ? ' · las dos participan en el hecho' : ' · solo se nombran'}
              </span>
            </li>
          ))}
        </ul>
      )}
    </li>
  );
}
