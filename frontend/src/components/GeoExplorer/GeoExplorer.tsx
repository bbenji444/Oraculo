/**
 * Pantalla "Geodatos": el globo con el catálogo de regiones de INEGI.
 *
 * Sirve para verificar visualmente la Fase 1 (capas, nombres, claves) y es
 * la base del globo de búsqueda de la Fase 6. Elige una región buscándola o
 * haciendo clic en el mapa; la tarjeta muestra sus datos y el mapa vuela a ella.
 */
import { useMemo, useState } from 'react';

import { useRegionDetail } from '../../hooks/useRegions';
import { GlobeMap, type MapSelection } from './GlobeMap';
import { MapLegend } from './MapLegend';
import { RegionCard } from './RegionCard';
import { SearchBox } from './SearchBox';

export function GeoExplorer() {
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const detail = useRegionDetail(selectedId);
  const data = detail.data;
  // Solo se vuela cuando llegó el detalle de la región elegida (y no el de la
  // anterior). useMemo evita un objeto nuevo en cada render: el mapa volaría
  // de nuevo cada vez que algo se redibuja.
  const selection = useMemo<MapSelection | null>(
    () => (data?.id === selectedId ? { id: data.id, level: data.level, bbox: data.bbox } : null),
    [data, selectedId],
  );

  return (
    <div className="relative h-full overflow-hidden bg-slate-950">
      <GlobeMap selection={selection} onPick={setSelectedId} />
      <aside className="absolute left-4 right-4 top-4 space-y-3 sm:right-auto sm:w-[22rem]">
        <SearchBox
          onSelect={(region) => {
            setSelectedId(region.id);
          }}
        />
        {selectedId !== null && (
          <RegionCard
            detail={detail.data}
            isLoading={detail.isPending}
            error={detail.error}
            onSelect={setSelectedId}
            onClose={() => {
              setSelectedId(null);
            }}
          />
        )}
      </aside>
      <div className="absolute bottom-8 left-4 hidden sm:block">
        <MapLegend />
      </div>
    </div>
  );
}
