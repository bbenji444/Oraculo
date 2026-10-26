/**
 * Tipos de lo que dibuja el motor del muro (Fases 9.1 y 9.6, ADR-0102).
 *
 * Nodos con su color y arcos con su confianza: el motor (`engine.ts`) no sabe
 * de casos, entidades ni notas.
 *
 * No hace: nada; son tipos.
 */
/** Un nodo listo para dibujar. */
export interface WallNode {
  id: string;
  label: string;
  /** Color del núcleo (tipo de entidad). */
  color: string;
  /** Color del borde (estatus legal). */
  ring: string;
  lng: number;
  lat: number;
  /** 1 = completo; menos = atenuado porque se eligió otro. */
  focus: number;
  selected: boolean;
}

/** Un arco listo para dibujar. */
export interface WallLink {
  id: string;
  from: string;
  to: string;
  /** Confirmado por una persona; los sugeridos se dibujan punteados. */
  confirmed: boolean;
  /** 0..1: grosor y brillo del arco (ya multiplicado por el realce). */
  confidence: number;
}

export interface WallCase {
  nodes: WallNode[];
  links: WallLink[];
}
