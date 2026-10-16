/**
 * Textos en español de niveles y claves, para que un analista entienda la
 * tarjeta sin conocer los nombres técnicos de la API.
 */
import type { RegionLevel } from '../../map/style';

export const LEVEL_LABEL: Record<RegionLevel, string> = {
  country: 'País',
  state: 'Estado',
  municipality: 'Municipio',
  locality: 'Localidad',
};

/**
 * Nombre de la clave según el nivel: los países usan código ISO; México, INEGI.
 *
 * @param level Nivel de la región.
 * @returns "Código ISO" o "Clave INEGI".
 */
export function codeLabel(level: RegionLevel): string {
  return level === 'country' ? 'Código ISO' : 'Clave INEGI';
}

/** Coordenadas legibles: "19.4330° N, 99.1482° O". */
export function formatPoint(lon: number, lat: number): string {
  const ns = lat >= 0 ? 'N' : 'S';
  const eo = lon >= 0 ? 'E' : 'O';
  return `${Math.abs(lat).toFixed(4)}° ${ns}, ${Math.abs(lon).toFixed(4)}° ${eo}`;
}
