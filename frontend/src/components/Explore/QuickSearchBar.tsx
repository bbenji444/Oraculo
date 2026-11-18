/**
 * Búsqueda rápida «como en el buscador de Google» (ADR-0110).
 *
 * La persona escribe lo que busca y presiona Enter: la IA propone las frases
 * y se busca con las fechas y las fuentes de la consulta, sin guardar un
 * concepto. Si el texto nombra un lugar («en Jalisco»), se busca ahí y queda
 * elegido en «Dónde»; si no, en la región de la consulta (México si no eligió). Los resultados se ven como
 * los de cualquier búsqueda; `KeepQuickSearch` ofrece guardarla después.
 *
 * Lo usan la consola del Centro de mando y el panel del diseño clásico.
 *
 * No hace: no estima el costo antes (la IA de las frases cuesta ~0.0001 USD y
 * la búsqueda usa los mismos topes que una normal).
 */
import { useId, useState } from 'react';

import { useKeepConcept } from '../../hooks/useConcepts';
import { useRegionsByLevel } from '../../hooks/useRegions';
import { useStartQuickSearch } from '../../hooks/useSearches';
import { quickSearchInput, useExplorerStore } from '../../store/explorer';
import { useQuickSearchStore } from '../../store/quickSearch';
import { Icon } from '../ui/Icon';

// El país del catálogo (INEGI + Natural Earth): región por defecto.
const MEXICO_CODE = 'MEX';

interface QuickSearchBarProps {
  /** Fuentes encendidas (`useSearchLauncher`); `undefined` mientras cargan. */
  providers: string[] | undefined;
  /** Si ya hay una búsqueda corriendo: no se lanza otra encima. */
  busy: boolean;
}

export function QuickSearchBar({ providers, busy }: QuickSearchBarProps) {
  const [text, setText] = useState('');
  const regionId = useExplorerStore((s) => s.regionId);
  const range = useExplorerStore((s) => s.range);
  const openSearch = useExplorerStore((s) => s.openSearch);
  const selectRegion = useExplorerStore((s) => s.selectRegion);
  const remember = useQuickSearchStore((s) => s.remember);
  const mexico = useRegionsByLevel('country').data?.find((r) => r.code === MEXICO_CODE);
  const start = useStartQuickSearch(({ placeRegionId, ...started }) => {
    remember({ ...started, text: text.trim() });
    // Se buscó en el lugar que nombró el texto: el mapa y «Dónde» lo muestran.
    if (placeRegionId !== null) selectRegion(placeRegionId);
    openSearch(started.searchId);
  });
  const id = useId();
  const input = quickSearchInput(text, { regionId, range }, mexico?.id ?? null, providers);
  const disabled = busy || start.isPending || input === null;

  return (
    <form
      role="search"
      aria-label="Búsqueda rápida"
      className="quick-search"
      onSubmit={(event) => {
        event.preventDefault();
        if (input && !disabled) start.mutate(input);
      }}
    >
      <label htmlFor={`${id}-q`} className="sr-only">
        Busca noticias como en Google
      </label>
      <div className="flex items-center gap-2">
        <Icon name="search" className="text-lg text-sky-300/80" />
        <input
          id={`${id}-q`}
          type="search"
          value={text}
          maxLength={500}
          autoComplete="off"
          placeholder="Busca noticias como en Google: robo de autos con violencia en Jalisco"
          onChange={(event) => {
            setText(event.target.value);
          }}
          className="hud-input min-w-0 flex-1"
        />
        <button
          type="submit"
          disabled={disabled}
          // Distinto del «Buscar» de la consulta con conceptos.
          aria-label="Búsqueda rápida"
          className="hud-btn hud-btn--sm shrink-0"
        >
          {start.isPending ? 'Buscando…' : 'Buscar'}
        </button>
      </div>
      {start.error ? (
        <p role="alert" className="mt-1 text-xs text-rose-300">
          {start.error.message}
        </p>
      ) : (
        <p className="mt-1 text-[11px] text-slate-500">
          Sin guardar un concepto: la IA arma las búsquedas y descarta las notas que no tratan de lo
          que escribiste. Si escribes un lugar («en Jalisco») se busca ahí; si no, en el de abajo
          {regionId === null ? ' (México)' : ''}. Las fechas son las de abajo.
        </p>
      )}
    </form>
  );
}

/**
 * «Guardar como concepto» la búsqueda rápida que se está viendo.
 *
 * Solo aparece en la búsqueda rápida que se acaba de lanzar; ya guardada,
 * dice «Guardado».
 */
export function KeepQuickSearch({ searchId }: { searchId: string }) {
  const last = useQuickSearchStore((s) => s.last);
  const markKept = useQuickSearchStore((s) => s.markKept);
  const keep = useKeepConcept();
  if (last?.searchId !== searchId) return null;
  if (last.kept) {
    return (
      <span className="flex items-center gap-1 text-[11px] text-emerald-300">
        <Icon name="check" /> Guardado en Conceptos
      </span>
    );
  }
  return (
    <span className="flex items-center gap-2">
      <button
        type="button"
        disabled={keep.isPending}
        title={`Guardar «${last.conceptName}» en Conceptos para volver a usarla`}
        onClick={() => {
          keep.mutate(last.conceptId, { onSuccess: markKept });
        }}
        className="hud-btn hud-btn--sm"
      >
        {keep.isPending ? 'Guardando…' : 'Guardar como concepto'}
      </button>
      {keep.error && <span className="text-[11px] text-rose-300">{keep.error.message}</span>}
    </span>
  );
}
