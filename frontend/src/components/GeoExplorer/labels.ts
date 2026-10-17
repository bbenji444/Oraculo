/**
 * Textos en español de los niveles de región, para que un analista entienda
 * el buscador sin conocer los nombres técnicos de la API.
 */
import type { RegionLevel } from '../../map/style';

export const LEVEL_LABEL: Record<RegionLevel, string> = {
  country: 'País',
  state: 'Estado',
  municipality: 'Municipio',
  locality: 'Localidad',
};
