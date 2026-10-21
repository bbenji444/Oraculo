/**
 * Buscador de regiones con autocompletado ("izta" → Alcaldía Iztapalapa).
 *
 * Accesible con teclado: flechas para moverse, Enter para elegir, Escape para
 * cerrar. Cada resultado dice su estado, para distinguir homónimos ("San Pedro"
 * de Coahuila o de Nuevo León). Los datos llegan con useRegionSearch y
 * useRegionsByLevel (nunca fetch directo).
 */
import { useId, useState } from 'react';

import { useRegionSearch, useRegionsByLevel } from '../../hooks/useRegions';
import type { Region } from '../../services/regions';
import { LEVEL_LABEL, stateOf } from './labels';

interface SearchBoxProps {
  onSelect: (region: Region) => void;
}

export function SearchBox({ onSelect }: SearchBoxProps) {
  const [query, setQuery] = useState('');
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const listId = useId();
  const search = useRegionSearch(query);
  const results = search.data ?? [];
  // La misma lista del filtro "Estado" (ya en caché): no es otra petición.
  const states = useRegionsByLevel('state').data;
  const showList = open && search.enabled;

  function choose(region: Region) {
    onSelect(region);
    setQuery(region.display_name);
    setOpen(false);
  }

  function onKeyDown(event: React.KeyboardEvent<HTMLInputElement>) {
    if (event.key === 'ArrowDown') {
      event.preventDefault();
      setOpen(true);
      setActive((i) => Math.min(i + 1, results.length - 1));
    } else if (event.key === 'ArrowUp') {
      event.preventDefault();
      setActive((i) => Math.max(i - 1, 0));
    } else if (event.key === 'Enter') {
      const region = results[active];
      if (region) choose(region);
    } else if (event.key === 'Escape') {
      setOpen(false);
    }
  }

  return (
    <div className="relative">
      <label htmlFor={`${listId}-input`} className="sr-only">
        Buscar estado, municipio o localidad
      </label>
      <div className="flex items-center gap-2 rounded-xl border border-slate-700/80 bg-slate-900/90 px-3 shadow-lg shadow-black/30 backdrop-blur focus-within:border-sky-500/70">
        <svg aria-hidden="true" viewBox="0 0 20 20" className="size-4 shrink-0 fill-slate-500">
          <path d="M8.5 3a5.5 5.5 0 0 1 4.38 8.82l3.65 3.65-1.06 1.06-3.65-3.65A5.5 5.5 0 1 1 8.5 3Zm0 1.5a4 4 0 1 0 0 8 4 4 0 0 0 0-8Z" />
        </svg>
        <input
          id={`${listId}-input`}
          role="combobox"
          aria-expanded={showList}
          aria-controls={listId}
          aria-autocomplete="list"
          autoComplete="off"
          spellCheck={false}
          value={query}
          placeholder="Busca: Iztapalapa, CDMX, Peñón Blanco…"
          onChange={(event) => {
            setQuery(event.target.value);
            setOpen(true);
            setActive(0);
          }}
          onFocus={() => {
            setOpen(true);
          }}
          onBlur={() => {
            // Espera un instante para que un clic en la lista alcance a registrarse.
            window.setTimeout(() => {
              setOpen(false);
            }, 150);
          }}
          onKeyDown={onKeyDown}
          className="w-full bg-transparent py-2.5 text-sm text-slate-100 placeholder:text-slate-500 focus:outline-none"
        />
        {search.isFetching && (
          <span
            aria-hidden="true"
            className="size-3.5 shrink-0 animate-spin rounded-full border-2 border-slate-600 border-t-sky-400"
          />
        )}
      </div>

      {showList && (
        <ul
          id={listId}
          role="listbox"
          className="absolute z-20 mt-2 max-h-80 w-full overflow-auto rounded-xl border border-slate-700/80 bg-slate-900/95 py-1 shadow-2xl shadow-black/50 backdrop-blur"
        >
          {search.error && (
            <li className="px-3 py-2 text-sm text-rose-300">{search.error.message}</li>
          )}
          {!search.error && search.isSuccess && results.length === 0 && (
            <li className="px-3 py-2 text-sm text-slate-400">Sin resultados.</li>
          )}
          {results.map((region, index) => {
            const state = stateOf(region, states);
            return (
              <li
                key={region.id}
                role="option"
                aria-selected={index === active}
                onMouseDown={(event) => {
                  event.preventDefault();
                  choose(region);
                }}
                onMouseEnter={() => {
                  setActive(index);
                }}
                className={`cursor-pointer px-3 py-2 text-sm ${
                  index === active ? 'bg-sky-500/15 text-slate-50' : 'text-slate-200'
                }`}
              >
                <span className="block truncate">{region.display_name}</span>
                <span className="block truncate text-xs text-slate-400">
                  {state && `${state} · `}
                  {LEVEL_LABEL[region.level]} · <span className="font-mono">{region.code}</span>
                </span>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
