/**
 * Lista de mis casos (Fase 9.3): nombre, estado, sensibilidad, cuántas notas
 * tiene y cuándo cambió. Dos pestañas: activos (abiertos y cerrados) y
 * archivados.
 *
 * No hace: no abre el caso (avisa con `onSelect`).
 */
import { useState } from 'react';

import { useCases } from '../../hooks/useCases';
import { caseSummary, SENSITIVITY_TONE, STATUS_TONE } from './labels';

interface CaseListProps {
  selectedId: string | null;
  onSelect: (id: string) => void;
}

export function CaseList({ selectedId, onSelect }: CaseListProps) {
  const [archived, setArchived] = useState(false);
  const cases = useCases(archived ? 'archived' : undefined);
  const items = cases.data ?? [];

  return (
    <div className="overflow-hidden rounded-xl border border-slate-800 bg-slate-900/40">
      <div className="flex gap-1 border-b border-slate-800 p-2" role="tablist">
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
            className={`rounded-lg px-3 py-1.5 text-xs transition-colors focus-visible:outline-2 focus-visible:outline-sky-400 ${
              archived === tab.key
                ? 'bg-sky-500/20 text-sky-100'
                : 'text-slate-400 hover:bg-slate-800'
            }`}
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
      <ul className="divide-y divide-slate-800">
        {items.map((item) => (
          <li key={item.id}>
            <button
              type="button"
              aria-current={item.id === selectedId}
              onClick={() => {
                onSelect(item.id);
              }}
              className={`w-full px-4 py-3 text-left transition-colors focus-visible:outline-2 focus-visible:outline-sky-400 ${
                item.id === selectedId ? 'bg-sky-500/10' : 'hover:bg-slate-800/60'
              }`}
            >
              <span className="flex flex-wrap items-center gap-2">
                <span className="font-medium text-slate-100">{item.name}</span>
                <span
                  className={`rounded-md px-1.5 py-0.5 text-[11px] ${STATUS_TONE[item.status]}`}
                >
                  {item.status_label}
                </span>
                <span
                  className={`rounded-md px-1.5 py-0.5 text-[11px] ${SENSITIVITY_TONE[item.sensitivity]}`}
                >
                  {item.sensitivity_label}
                </span>
              </span>
              <span className="mt-0.5 block text-xs text-slate-400">{caseSummary(item)}</span>
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
