/**
 * Elegir la región de la búsqueda (§14.2 "Sincronización"):
 *
 * - buscador por nombre o alias;
 * - migas de pan (México › Jalisco › Guadalajara), cada nivel clickeable para subir;
 * - filtros encadenados Estado → Municipio → Localidad.
 *
 * Todo escribe en el store (`selectRegion`), igual que el clic en el globo:
 * mapa y filtros nunca se desincronizan.
 */
import { useState } from 'react';

import { useChildRegions, useRegionDetail, useRegionsByLevel } from '../../hooks/useRegions';
import { MAX_FILTER_OPTIONS } from '../../services/regions';
import { useExplorerStore } from '../../store/explorer';
import { SearchBox } from '../GeoExplorer/SearchBox';
import { chainOf } from './regionChain';

// Campo de la consola táctica (ADR-0036). Va dentro de una etiqueta Orbitron en
// mayúsculas: la letra del menú se regresa a la normal.
const SELECT = 'hud-input px-2 py-1.5 font-sans tracking-normal normal-case';

interface LevelSelectProps {
  label: string;
  value: number | null;
  options: { id: number; name: string }[] | undefined;
  disabled: boolean;
  onChange: (id: number | null) => void;
  placeholder: string;
}

function LevelSelect({ label, value, options, disabled, onChange, placeholder }: LevelSelectProps) {
  return (
    <label className="hud-label mb-0">
      {label}
      <select
        className={`${SELECT} mt-1.5`}
        value={value ?? ''}
        disabled={disabled}
        onChange={(event) => {
          onChange(event.target.value === '' ? null : Number(event.target.value));
        }}
      >
        <option value="">{placeholder}</option>
        {options?.map((option) => (
          <option key={option.id} value={option.id}>
            {option.name}
          </option>
        ))}
      </select>
    </label>
  );
}

export function RegionPicker() {
  const regionId = useExplorerStore((s) => s.regionId);
  const selectRegion = useExplorerStore((s) => s.selectRegion);
  const detail = useRegionDetail(regionId).data;
  const { stateId, municipalityId, localityId } = chainOf(detail);
  const states = useRegionsByLevel('state').data;
  const municipalities = useChildRegions(stateId).data;
  const localities = useChildRegions(municipalityId).data;
  // Filtro de texto para las localidades: un municipio puede tener cientos.
  const [localityFilter, setLocalityFilter] = useState('');
  const shownLocalities = localities?.filter((l) =>
    l.name.toLowerCase().includes(localityFilter.trim().toLowerCase()),
  );

  return (
    <div className="space-y-3">
      <SearchBox
        onSelect={(region) => {
          selectRegion(region.id);
        }}
      />
      {detail && (
        <nav aria-label="Región elegida" className="flex flex-wrap items-center gap-1 text-xs">
          {detail.ancestors.map((ancestor) => (
            <span key={ancestor.id} className="flex items-center gap-1">
              <button
                type="button"
                onClick={() => {
                  selectRegion(ancestor.id);
                }}
                className="rounded text-sky-300 hover:text-sky-200 hover:underline focus-visible:outline-2 focus-visible:outline-sky-400"
              >
                {ancestor.name}
              </button>
              <span aria-hidden="true" className="text-slate-600">
                ›
              </span>
            </span>
          ))}
          <span className="font-medium text-slate-100">{detail.display_name}</span>
        </nav>
      )}
      <div className="grid grid-cols-2 gap-2">
        <LevelSelect
          label="Estado"
          value={stateId}
          options={states}
          disabled={!states}
          placeholder="Todo México"
          onChange={(id) => {
            const mexico = detail?.ancestors.find((a) => a.level === 'country');
            selectRegion(id ?? mexico?.id ?? null);
          }}
        />
        <LevelSelect
          label="Municipio"
          value={municipalityId}
          options={municipalities}
          disabled={stateId === null}
          placeholder="Todo el estado"
          onChange={(id) => {
            selectRegion(id ?? stateId);
          }}
        />
      </div>
      {municipalityId !== null && (
        <div className="space-y-1.5">
          <input
            type="search"
            value={localityFilter}
            onChange={(event) => {
              setLocalityFilter(event.target.value);
            }}
            placeholder="Filtrar localidades…"
            aria-label="Filtrar localidades"
            className={SELECT}
          />
          <LevelSelect
            label="Localidad"
            value={localityId}
            options={shownLocalities}
            disabled={!localities}
            placeholder="Todo el municipio"
            onChange={(id) => {
              selectRegion(id ?? municipalityId);
            }}
          />
          {localities?.length === MAX_FILTER_OPTIONS && (
            <p className="text-[11px] text-slate-500">
              Se muestran las primeras {MAX_FILTER_OPTIONS}; para otras usa el buscador.
            </p>
          )}
        </div>
      )}
    </div>
  );
}
