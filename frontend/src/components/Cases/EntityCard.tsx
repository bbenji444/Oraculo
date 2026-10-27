/**
 * Una entidad propuesta por la IA en un caso (Fase 9.4, historia H9.2).
 *
 * Muestra tipo, nombre, estatus legal (siempre visible, §9.10) y cuántas
 * menciones tiene; al desplegarla, cada cita con la nota de donde salió. Quien
 * puede editar la confirma (en personas, eligiendo el estatus legal según la
 * nota; no existe "culpable") o la descarta.
 *
 * Desde la 9.5 (§9.8) también muestra qué entidades se le unieron (con
 * «Separar»), permite decir «Es la misma que…» otra entidad del caso y separar
 * menciones propias en una sugerencia nueva cuando juntó a dos homónimos.
 *
 * No hace: no pide datos (los recibe de `CaseEntities`).
 */
import { useState } from 'react';

import type { ResolutionAction } from '../../hooks/useResolution';
import type { Entity, LegalStatus } from '../../services/entities';
import { formatDay } from '../Explore/format';
import { LEGAL_STATUS_OPTIONS, mergeAction } from './labels';
import { ExternalLink } from '../ExternalLink';

interface EntityCardProps {
  entity: Entity;
  canEdit: boolean;
  busy: boolean;
  onConfirm: (legal: LegalStatus | undefined) => void;
  onDiscard: () => void;
  /** Otras entidades del caso del mismo tipo con las que se puede unir (9.5). */
  mergeTargets: Entity[];
  onResolve: (action: ResolutionAction) => void;
}

// Botones chicos de la consola táctica (ADR-0036): confirmar en verde, descartar en rojo.
const BUTTON = 'hud-btn hud-btn--sm';

export function EntityCard({
  entity,
  canEdit,
  busy,
  onConfirm,
  onDiscard,
  mergeTargets,
  onResolve,
}: EntityCardProps) {
  const [open, setOpen] = useState(false);
  const [target, setTarget] = useState(0);
  const [split, setSplit] = useState<number[]>([]);
  const own = entity.mentions.filter((m) => m.entity_id === entity.id);
  const canSplit = canEdit && own.length > 1;
  const isPerson = entity.type === 'person';
  const [legal, setLegal] = useState<LegalStatus>(
    entity.legal_status ?? entity.suggested_legal_status ?? 'mentioned',
  );
  const status = entity.legal_status_label ?? entity.suggested_legal_status_label;

  return (
    <li className="hud-reveal px-5 py-3.5 transition-colors duration-300 hover:bg-sky-400/[0.03]">
      <div className="flex flex-wrap items-start gap-3">
        <div className="min-w-0 flex-1">
          <p className="text-sm text-slate-100">
            <span className="mr-2 rounded-md border border-sky-400/20 bg-sky-400/5 px-1.5 py-0.5 text-[11px] text-slate-200">
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
          {entity.merged.length > 0 && (
            <p className="mt-1 text-xs text-slate-400">
              Se le unió:{' '}
              {entity.merged.map((m, index) => (
                <span key={m.id}>
                  {index > 0 && ', '}
                  <span className="text-slate-200">{m.label}</span>
                  {canEdit && (
                    <button
                      type="button"
                      disabled={busy}
                      onClick={() => {
                        onResolve({ kind: 'unmerge', entityId: m.id });
                      }}
                      className="ml-1 text-sky-300 hover:underline disabled:opacity-50"
                    >
                      (separar)
                    </button>
                  )}
                </span>
              ))}
            </p>
          )}
          {canEdit && entity.review_status !== 'discarded' && mergeTargets.length > 0 && (
            <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-slate-400">
              <label htmlFor={`unir-${String(entity.id)}`}>Es la misma que</label>
              <select
                id={`unir-${String(entity.id)}`}
                value={target}
                onChange={(event) => {
                  setTarget(Number(event.target.value));
                }}
                className="max-w-[16rem] hud-input w-auto px-2 py-1 text-xs"
              >
                <option value={0}>elige…</option>
                {mergeTargets.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.label} ({t.review_status_label})
                  </option>
                ))}
              </select>
              {target > 0 && (
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => {
                    const chosen = mergeTargets.find((t) => t.id === target);
                    if (chosen) onResolve(mergeAction(entity, chosen));
                    setTarget(0);
                  }}
                  className={`${BUTTON} border-emerald-400/50 text-emerald-100`}
                >
                  Unir
                </button>
              )}
            </div>
          )}
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
                className="hud-input w-auto px-2 py-1 text-xs"
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
                className={`${BUTTON} border-emerald-400/50 text-emerald-100`}
              >
                Confirmar
              </button>
            )}
            {entity.review_status !== 'discarded' && (
              <button
                type="button"
                disabled={busy}
                onClick={onDiscard}
                className={`${BUTTON} hud-btn--danger`}
              >
                Descartar
              </button>
            )}
          </div>
        )}
      </div>
      {open && (
        <ul className="mt-2 space-y-2 border-l-2 border-sky-400/30 pl-3">
          {entity.mentions.map((m) => (
            <li key={m.id} className="text-xs">
              <blockquote className="text-slate-200">
                {canSplit && m.entity_id === entity.id && (
                  <input
                    type="checkbox"
                    aria-label={`Separar la mención «${m.evidence_span}»`}
                    checked={split.includes(m.id)}
                    onChange={(event) => {
                      setSplit(
                        event.target.checked ? [...split, m.id] : split.filter((id) => id !== m.id),
                      );
                    }}
                    className="mr-2 align-middle"
                  />
                )}
                «{m.evidence_span}»
              </blockquote>
              <p className="mt-0.5 text-slate-400">
                <ExternalLink href={m.article_url} className="text-sky-300 hover:underline">
                  {m.article_title} ↗
                </ExternalLink>
                {m.source_name && ` · ${m.source_name}`}
                {m.published_at && ` · ${formatDay(m.published_at)}`}
                {m.legal_status_hint_label && ` · la nota dice: ${m.legal_status_hint_label}`}
              </p>
            </li>
          ))}
          {canSplit && (
            <li className="text-xs text-slate-400">
              ¿Son dos personas distintas con el mismo nombre? Marca las menciones de la otra y{' '}
              <button
                type="button"
                disabled={busy || split.length === 0 || split.length === own.length}
                onClick={() => {
                  onResolve({ kind: 'split', entityId: entity.id, mentionIds: split });
                  setSplit([]);
                }}
                className="text-sky-300 hover:underline disabled:text-slate-500 disabled:no-underline"
              >
                sepáralas en otra entidad
              </button>
              .
            </li>
          )}
        </ul>
      )}
    </li>
  );
}
