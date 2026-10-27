/**
 * Clases compartidas del Centro de mando (styles/mando.css).
 */
import { GLASS } from '../Explore/ui';

/**
 * Panel de vidrio del Centro de mando: el de la consola táctica, pero
 * translúcido, para que se vea el globo detrás (Benji, 27/10/2026: «que no sea
 * tan azul, sino tono vidrio para que se pueda ver la parte de atrás»). Sin
 * `backdrop-filter`: desenfocar el globo cada cuadro reiniciaba la tarjeta
 * Intel (ADR-0036).
 */
export const MANDO_GLASS = `${GLASS} mando-glass`;
