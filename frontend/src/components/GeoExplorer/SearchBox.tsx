/**
 * Buscador de regiones con autocompletado ("izta" → Alcaldía Iztapalapa).
 *
 * Accesible con teclado: flechas para moverse, Enter para elegir, Escape para
 * cerrar. Cada resultado dice su estado, para distinguir homónimos ("San Pedro"
 * de Coahuila o de Nuevo León). Los datos llegan con useRegionSearch y
 * useRegionsByLevel (nunca fetch directo).
 *
 * Diseño «consola táctica» (ADR-0036): campo con haz de enfoque y lista que
 * se despliega con la opción activa iluminada. Sin desenfoque de fondo: el
 * globo ya usa la tarjeta de video.
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
      <div className="hud-field shadow-lg shadow-black/30">
        <svg aria-hidden="true" viewBox="0 0 20 20" className="size-4 shrink-0 fill-sky-300/70">
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
          className="hud-reveal absolute z-20 mt-2 max-h-80 w-full overflow-auto rounded-xl border border-sky-400/30 bg-[#050d12]/[0.97] py-1 shadow-2xl shadow-black/60"
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
                className={`cursor-pointer border-l-2 px-3 py-2 text-sm transition-colors duration-200 ${
                  index === active
                    ? 'border-sky-400 bg-sky-400/10 text-slate-50'
                    : 'border-transparent text-slate-200'
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
