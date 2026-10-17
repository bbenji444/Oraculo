/**
 * Estado, municipio y localidad de la región elegida, para los filtros
 * encadenados (§14.2): salen de la región y de sus ancestros.
 */
import type { RegionDetail } from '../../services/regions';

/** Ids del estado, municipio y localidad de la región elegida. */
export interface RegionChain {
  stateId: number | null;
  municipalityId: number | null;
  localityId: number | null;
}

/**
 * Arma la cadena a partir de la región y sus ancestros.
 *
 * @example chainOf(guadalajara) // { stateId: 14, municipalityId: 1084, localityId: null }
 */
export function chainOf(detail: RegionDetail | undefined): RegionChain {
  const chain: RegionChain = { stateId: null, municipalityId: null, localityId: null };
  if (!detail) return chain;
  for (const ref of [...detail.ancestors, detail]) {
    if (ref.level === 'state') chain.stateId = ref.id;
    if (ref.level === 'municipality') chain.municipalityId = ref.id;
    if (ref.level === 'locality') chain.localityId = ref.id;
  }
  return chain;
}
