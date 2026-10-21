/**
 * Textos en español de los niveles de región, para que un analista entienda
 * el buscador sin conocer los nombres técnicos de la API, y el estado de cada
 * resultado para distinguir homónimos ("San Pedro" de Coahuila o de Nuevo León).
 */
import type { RegionLevel } from '../../map/style';
import type { Region } from '../../services/regions';

export const LEVEL_LABEL: Record<RegionLevel, string> = {
  country: 'País',
  state: 'Estado',
  municipality: 'Municipio',
  locality: 'Localidad',
};

// La clave INEGI de un municipio o localidad empieza con la de su estado
// (2 dígitos, ADR-0002).
const STATE_CODE_LENGTH = 2;
const MEXICO = 'MEX';

/**
 * Estado al que pertenece un municipio o una localidad de México.
 *
 * @param region Resultado del buscador (nivel, clave y país).
 * @param states Estados del catálogo; `undefined` mientras cargan.
 * @returns El nombre del estado, o `null` si es un país o un estado, si es de
 *   otro país o si la clave no corresponde a ningún estado cargado.
 *
 * @example
 * stateOf({ level: 'municipality', code: '05033', country_code: 'MEX' }, states)
 * // 'Coahuila de Zaragoza'
 */
export function stateOf(
  region: Pick<Region, 'level' | 'code' | 'country_code'>,
  states: readonly Pick<Region, 'code' | 'name'>[] | undefined,
): string | null {
  if (region.level !== 'municipality' && region.level !== 'locality') return null;
  if (region.country_code !== MEXICO || !states) return null;
  const code = region.code.slice(0, STATE_CODE_LENGTH);
  return states.find((s) => s.code === code)?.name ?? null;
}
