/**
 * Elegir la región de un envío programado: buscador y filtros Estado →
 * Municipio, como en Explorar (ADR-0046).
 *
 * No hace: no escribe en el store de Explorar; avisa con `onChange`, porque
 * la región de un envío no es la de la búsqueda abierta.
 */
import { useId } from 'react';

import { useChildRegions, useRegionDetail, useRegionsByLevel } from '../../hooks/useRegions';
import { chainOf } from '../Explore/regionChain';
import { SearchBox } from '../GeoExplorer/SearchBox';
import { HudSelect } from '../ui/HudSelect';

interface RegionFieldProps {
  value: number | null;
  onChange: (id: number) => void;
}

export function RegionField({ value, onChange }: RegionFieldProps) {
  const id = useId();
  const detail = useRegionDetail(value).data;
  const { stateId, municipalityId } = chainOf(detail);
  const states = useRegionsByLevel('state').data;
  // México es el país de los estados (todos traen su id en parent_id).
  const mexicoId = states?.[0]?.parent_id ?? null;
  const municipalities = useChildRegions(stateId).data;

  return (
    <div className="space-y-2">
      <SearchBox
        onSelect={(region) => {
          onChange(region.id);
        }}
      />
      <p className="text-xs text-slate-400">
        Elegida: <b className="text-slate-100">{detail?.display_name ?? 'Todo México'}</b>
      </p>
      <div className="grid grid-cols-2 gap-2">
        <div>
          <label htmlFor={`${id}-state`} className="hud-label">
            Estado
          </label>
          <HudSelect
            id={`${id}-state`}
            size="sm"
            value={stateId === null ? '' : String(stateId)}
            disabled={!states}
            options={[
              { value: '', label: 'Todo México' },
              ...(states ?? []).map((s) => ({ value: String(s.id), label: s.name })),
            ]}
            onChange={(next) => {
              const chosen = next === '' ? mexicoId : Number(next);
              if (chosen !== null) onChange(chosen);
            }}
          />
        </div>
        <div>
          <label htmlFor={`${id}-municipality`} className="hud-label">
            Municipio
          </label>
          <HudSelect
            id={`${id}-municipality`}
            size="sm"
            value={municipalityId === null ? '' : String(municipalityId)}
            disabled={stateId === null}
            options={[
              { value: '', label: 'Todo el estado' },
              ...(municipalities ?? []).map((m) => ({ value: String(m.id), label: m.name })),
            ]}
            onChange={(next) => {
              const chosen = next === '' ? stateId : Number(next);
              if (chosen !== null) onChange(chosen);
            }}
          />
        </div>
      </div>
    </div>
  );
}
