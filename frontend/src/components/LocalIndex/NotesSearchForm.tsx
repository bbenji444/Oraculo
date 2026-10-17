/**
 * Formulario de la pestaña "Notas": concepto, región y rango de días.
 *
 * Solo junta la elección y la entrega con onSearch; la búsqueda la hace el
 * hook de la página. Los conceptos llegan con useConcepts.
 */
import { useState } from 'react';

import { useConcepts } from '../../hooks/useConcepts';
import type { Region } from '../../services/regions';
import { SearchBox } from '../GeoExplorer/SearchBox';

// Rangos del panel de búsqueda (especificación §14.3).
const RANGES = [
  { days: 1, label: 'Hoy' },
  { days: 7, label: '7 días' },
  { days: 30, label: '30 días' },
];

export interface NotesSearch {
  conceptId: number;
  regionId: number;
  days: number;
}

interface NotesSearchFormProps {
  searching: boolean;
  onSearch: (search: NotesSearch) => void;
}

export function NotesSearchForm({ searching, onSearch }: NotesSearchFormProps) {
  const concepts = useConcepts();
  const [conceptId, setConceptId] = useState<number | null>(null);
  const [region, setRegion] = useState<Region | null>(null);
  const [days, setDays] = useState(7);
  const ready = conceptId !== null && region !== null;

  return (
    <div className="space-y-2">
      <div className="grid gap-2 sm:grid-cols-[minmax(0,14rem)_minmax(0,1fr)]">
        <label className="text-xs text-slate-400">
          Concepto
          <select
            value={conceptId ?? ''}
            onChange={(event) => {
              setConceptId(event.target.value ? Number(event.target.value) : null);
            }}
            className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-2 py-1.5 text-sm text-slate-100 focus-visible:outline-2 focus-visible:outline-sky-400"
          >
            <option value="">Elige un concepto…</option>
            {(concepts.data ?? [])
              .filter((concept) => concept.is_active)
              .map((concept) => (
                <option key={concept.id} value={concept.id}>
                  {concept.name}
                </option>
              ))}
          </select>
        </label>
        <div className="text-xs text-slate-400">
          Región
          <div className="mt-1">
            <SearchBox onSelect={setRegion} />
          </div>
        </div>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <div role="radiogroup" aria-label="Rango de fechas" className="flex gap-1">
          {RANGES.map((range) => (
            <button
              key={range.days}
              type="button"
              role="radio"
              aria-checked={days === range.days}
              onClick={() => {
                setDays(range.days);
              }}
              className={`rounded-md px-2.5 py-1 text-xs focus-visible:outline-2 focus-visible:outline-sky-400 ${
                days === range.days
                  ? 'bg-slate-700 text-slate-50'
                  : 'text-slate-400 hover:bg-slate-800 hover:text-slate-200'
              }`}
            >
              {range.label}
            </button>
          ))}
        </div>
        <button
          type="button"
          disabled={!ready || searching}
          onClick={() => {
            if (conceptId !== null && region !== null) {
              onSearch({ conceptId, regionId: region.id, days });
            }
          }}
          className="ml-auto rounded-lg bg-sky-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-sky-500 focus-visible:outline-2 focus-visible:outline-sky-300 disabled:cursor-not-allowed disabled:opacity-40"
        >
          {searching ? 'Buscando…' : 'Buscar notas'}
        </button>
      </div>
      {!ready && (
        <p className="text-xs text-slate-500">
          Elige un concepto y una región, por ejemplo Extorsión en Jalisco.
        </p>
      )}
    </div>
  );
}
