/**
 * Lista de mis casos (Fase 9.3): nombre, estado, sensibilidad, cuántas notas
 * tiene y cuándo cambió. Dos pestañas: activos (abiertos y cerrados) y
 * archivados.
 *
 * Diseño «consola táctica» (ADR-0036): las pestañas son un selector con
 * pastilla deslizante y cada caso una fila que se ilumina, con insignias y una
 * flecha que se adelanta.
 *
 * No hace: no abre el caso (avisa con `onSelect`).
 */
import { type CSSProperties, useState } from 'react';

import { useCases } from '../../hooks/useCases';
import { caseSummary, SENSITIVITY_TONE, STATUS_TONE } from './labels';
import { ArrowIcon } from '../ui/HudButton';
import { HudChip } from '../ui/HudChip';
import { HudPanel } from '../ui/HudPanel';

interface CaseListProps {
  selectedId: string | null;
  onSelect: (id: string) => void;
}

export function CaseList({ selectedId, onSelect }: CaseListProps) {
  const [archived, setArchived] = useState(false);
  const cases = useCases(archived ? 'archived' : undefined);
  const items = cases.data ?? [];

  return (
    <HudPanel className="overflow-hidden p-2">
      <div
        className="hud-seg mb-2"
        role="tablist"
        style={{ '--seg-i': archived ? 1 : 0, '--seg-n': 2 } as CSSProperties}
      >
        {[
          { key: false, label: 'Activos' },
          { key: true, label: 'Archivados' },
        ].map((tab) => (
          <button
            key={tab.label}
            type="button"
            role="tab"
            aria-selected={archived === tab.key}
            onClick={() => {
              setArchived(tab.key);
            }}
            className="focus-visible:outline-2 focus-visible:outline-sky-400"
          >
            {tab.label}
          </button>
        ))}
      </div>
      {cases.isPending && <p className="p-4 text-sm text-slate-400">Cargando casos…</p>}
      {cases.error && (
        <p role="alert" className="p-4 text-sm text-rose-300">
          {cases.error.message}
        </p>
      )}
      {cases.isSuccess && items.length === 0 && (
        <p className="p-4 text-sm text-slate-400">
          {archived
            ? 'No hay casos archivados.'
            : 'Todavía no tienes casos. Crea uno y agrega noticias desde Explorar.'}
        </p>
      )}
      <ul>
        {items.map((item, index) => (
          <li key={item.id} className="hud-reveal" style={{ '--i': index } as CSSProperties}>
            <button
              type="button"
              aria-current={item.id === selectedId}
              onClick={() => {
                onSelect(item.id);
              }}
              className="hud-row w-full text-left focus-visible:outline-2 focus-visible:outline-sky-400"
            >
              <span className="min-w-0 flex-1">
                <span className="line-clamp-2 block font-medium text-slate-50">{item.name}</span>
                <span className="mt-1 block text-xs text-slate-400">{caseSummary(item)}</span>
              </span>
              <span className="flex shrink-0 flex-wrap justify-end gap-1.5">
                <HudChip tone={STATUS_TONE[item.status]} dot>
                  {item.status_label}
                </HudChip>
                <HudChip tone={SENSITIVITY_TONE[item.sensitivity]}>
                  {item.sensitivity_label}
                </HudChip>
              </span>
              <span className="hud-row-arrow">
                <ArrowIcon />
              </span>
            </button>
          </li>
        ))}
      </ul>
    </HudPanel>
  );
}
