/**
 * Una entidad propuesta por la IA en un caso (Fase 9.4, historia H9.2).
 *
 * Muestra tipo, nombre, estatus legal (siempre visible, §9.10) y cuántas
 * menciones tiene; al desplegarla, cada cita con la nota de donde salió. Quien
 * puede editar la confirma (en personas, eligiendo el estatus legal según la
 * nota; no existe "culpable") o la descarta.
 *
 * No hace: no pide datos (los recibe de `CaseEntities`).
 */
import { useState } from 'react';

import type { Entity, LegalStatus } from '../../services/entities';
import { formatDay } from '../Explore/format';
import { LEGAL_STATUS_OPTIONS } from './labels';

interface EntityCardProps {
  entity: Entity;
  canEdit: boolean;
  busy: boolean;
  onConfirm: (legal: LegalStatus | undefined) => void;
  onDiscard: () => void;
}

const BUTTON =
  'rounded-lg px-2.5 py-1 text-xs font-medium focus-visible:outline-2 focus-visible:outline-sky-400 disabled:opacity-50';

export function EntityCard({ entity, canEdit, busy, onConfirm, onDiscard }: EntityCardProps) {
  const [open, setOpen] = useState(false);
  const isPerson = entity.type === 'person';
  const [legal, setLegal] = useState<LegalStatus>(
    entity.legal_status ?? entity.suggested_legal_status ?? 'mentioned',
  );
  const status = entity.legal_status_label ?? entity.suggested_legal_status_label;

  return (
    <li className="px-4 py-3">
      <div className="flex flex-wrap items-start gap-3">
        <div className="min-w-0 flex-1">
          <p className="text-sm text-slate-100">
            <span className="mr-2 rounded-md bg-slate-800 px-1.5 py-0.5 text-[11px] text-slate-300">
              {entity.type_label}
            </span>
            {entity.label}
          </p>
          <p className="mt-1 text-xs text-slate-400">
            {isPerson && (
              <span className="mr-2 font-medium text-amber-200">
                {status ? `Estatus: ${status}` : 'Estatus: la nota no lo dice'}
                {!entity.legal_status && status ? ' (sugerido por la IA)' : ''}
              </span>
            )}
            {entity.aliases.length > 0 && `También: ${entity.aliases.join(', ')} · `}
            {entity.region_name && `${entity.region_name} · `}
            <button
              type="button"
              aria-expanded={open}
              onClick={() => {
                setOpen(!open);
              }}
              className="text-sky-300 underline-offset-2 hover:underline"
            >
              {entity.mention_count} {entity.mention_count === 1 ? 'mención' : 'menciones'} en{' '}
              {entity.article_count} {entity.article_count === 1 ? 'nota' : 'notas'}
            </button>
            {entity.reviewed_by &&
              ` · ${entity.review_status_label} por ${entity.reviewed_by}${
                entity.reviewed_at ? ` el ${formatDay(entity.reviewed_at)}` : ''
              }`}
          </p>
        </div>
        {canEdit && (
          <div className="flex shrink-0 flex-wrap items-center gap-2">
            {isPerson && (
              <select
                aria-label={`Estatus legal de ${entity.label}`}
                value={legal}
                onChange={(event) => {
                  setLegal(event.target.value as LegalStatus);
                }}
                className="rounded-md border border-slate-700 bg-slate-900 px-1.5 py-1 text-xs text-slate-100"
              >
                {LEGAL_STATUS_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            )}
            {(entity.review_status !== 'confirmed' || entity.legal_status !== legal) && (
              <button
                type="button"
                disabled={busy}
                onClick={() => {
                  onConfirm(isPerson ? legal : undefined);
                }}
                className={`${BUTTON} bg-emerald-500/20 text-emerald-100 hover:bg-emerald-500/30`}
              >
                Confirmar
              </button>
            )}
            {entity.review_status !== 'discarded' && (
              <button
                type="button"
                disabled={busy}
                onClick={onDiscard}
                className={`${BUTTON} text-rose-300 hover:bg-rose-500/10`}
              >
                Descartar
              </button>
            )}
          </div>
        )}
      </div>
      {open && (
        <ul className="mt-2 space-y-2 border-l border-slate-700 pl-3">
          {entity.mentions.map((m) => (
            <li key={`${String(m.article_id)}-${m.evidence_span}`} className="text-xs">
              <blockquote className="text-slate-200">«{m.evidence_span}»</blockquote>
              <p className="mt-0.5 text-slate-400">
                <a
                  href={m.article_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-sky-300 hover:underline"
                >
                  {m.article_title} ↗
                </a>
                {m.source_name && ` · ${m.source_name}`}
                {m.published_at && ` · ${formatDay(m.published_at)}`}
                {m.legal_status_hint_label && ` · la nota dice: ${m.legal_status_hint_label}`}
              </p>
            </li>
          ))}
        </ul>
      )}
    </li>
  );
}
