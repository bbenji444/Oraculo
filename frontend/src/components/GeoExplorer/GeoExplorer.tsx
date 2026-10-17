/**
 * Pantalla "Geodatos": el globo con el catálogo de regiones de INEGI.
 *
 * Sirve para verificar visualmente la Fase 1 (capas, nombres, claves) y es
 * la base del globo de búsqueda de la Fase 6. Elige una región buscándola o
 * haciendo clic en el mapa; la tarjeta muestra sus datos y el mapa vuela a ella.
 * Al entrar, el globo gira despacio; se detiene al tocarlo o al elegir una
 * región, y el botón "Girar globo" lo reanuda.
 */
import { useCallback, useMemo, useState } from 'react';

import { useRegionDetail } from '../../hooks/useRegions';
import { prefersReducedMotion } from '../../map/spin';
import type { EarthMode } from '../../map/style';
import { SpaceBackground } from '../Space/SpaceBackground';
import { EarthToggle } from './EarthToggle';
import { GlobeMap, type MapSelection } from './GlobeMap';
import { MapLegend } from './MapLegend';
import { RegionCard } from './RegionCard';
import { SearchBox } from './SearchBox';
import { SpinToggle } from './SpinToggle';

export function GeoExplorer() {
  const [selectedId, setSelectedId] = useState<number | null>(null);
  // Gira al entrar, salvo que el sistema pida menos movimiento.
  const [spinning, setSpinning] = useState(() => !prefersReducedMotion());
  // De noche por defecto, con las ciudades iluminadas (decisión de Benji, ADR-0017).
  const [earth, setEarth] = useState<EarthMode>('night');
  const stopSpinning = useCallback(() => {
    setSpinning(false);
  }, []);

  function select(regionId: number | null) {
    // Elegir una región detiene el giro: la cámara vuela hacia ella.
    if (regionId !== null) setSpinning(false);
    setSelectedId(regionId);
  }
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
    <div className="relative h-full overflow-hidden bg-[#02030a]">
      <SpaceBackground />
      <GlobeMap
        selection={selection}
        onPick={select}
        spinning={spinning}
        onUserInteract={stopSpinning}
        earth={earth}
      />
      <aside className="absolute left-4 right-4 top-4 space-y-3 sm:right-auto sm:w-[22rem]">
        <SearchBox
          onSelect={(region) => {
            select(region.id);
          }}
        />
        {selectedId !== null && (
          <RegionCard
            detail={detail.data}
            isLoading={detail.isPending}
            error={detail.error}
            onSelect={select}
            onClose={() => {
              select(null);
            }}
          />
        )}
      </aside>
      <div className="absolute bottom-8 left-4 hidden space-y-2 sm:block">
        <SpinToggle
          spinning={spinning}
          onToggle={() => {
            setSpinning((current) => !current);
          }}
        />
        <EarthToggle earth={earth} onChange={setEarth} />
        <MapLegend />
      </div>
    </div>
  );
}
