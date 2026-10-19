/**
 * Créditos del mapa (INEGI, Natural Earth, NASA, OpenStreetMap) plegados al
 * iniciar: solo se ve el botón "i" y los créditos aparecen al hacer clic
 * (decisión de Benji, para que nada tape el globo).
 *
 * Por qué hace falta: en modo compacto, MapLibre 6.14 abre la atribución sola
 * en cuanto llegan los créditos de las fuentes, y solo la pliega cuando la
 * persona arrastra el mapa (`drag`, en attribution_control.ts). El giro
 * automático del globo no es un arrastre, así que se quedaba abierta.
 *
 * Se pliega con un clic en el propio botón de MapLibre: es el mismo camino
 * que un clic de la persona, y después el botón sigue funcionando igual.
 *
 * No hace: no cambia los créditos ni los quita (las licencias los piden).
 */

const CONTROL = '.maplibregl-ctrl-attrib';
const BUTTON = '.maplibregl-ctrl-attrib-button';
const SHOW = 'maplibregl-compact-show';

/**
 * Pliega la atribución la primera vez que MapLibre la abre.
 *
 * @param mapContainer Contenedor del mapa (`map.getContainer()`).
 * @returns Función para dejar de vigilar (al desmontar el mapa).
 */
export function collapseAttributionOnStart(mapContainer: HTMLElement): () => void {
  const control = mapContainer.querySelector<HTMLElement>(CONTROL);
  if (!control) return () => undefined;

  const collapse = (): boolean => {
    if (!control.classList.contains(SHOW)) return false;
    control.querySelector<HTMLElement>(BUTTON)?.click();
    return true;
  };

  if (collapse()) return () => undefined;
  const observer = new MutationObserver(() => {
    // Solo la primera vez: después, abrir y cerrar es decisión de la persona.
    if (collapse()) observer.disconnect();
  });
  observer.observe(control, { attributes: true, attributeFilter: ['class'] });
  return () => {
    observer.disconnect();
  };
}
