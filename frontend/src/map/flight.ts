/**
 * Vuelos más fluidos: el globo se dibuja con menos resolución mientras vuela y
 * recupera la nitidez al aterrizar (§14.2, ADR-0017).
 *
 * Por qué: el mapa está limitado por cuántos píxeles pinta en cada cuadro. Medido
 * en Explorar a 1920×1080 con escala de Windows 125 % (20/10/2026), el mismo
 * vuelo de México a la CDMX (3 s):
 *   - resolución 1.25 (la de la pantalla): ~37 cuadros/s, 30 % de cuadros lentos;
 *   - 1.0: ~46 cuadros/s, 12 %;
 *   - 0.8: ~55 cuadros/s, 4 %.
 * En movimiento la pérdida de nitidez casi no se nota; al aterrizar vuelve.
 *
 * Solo para los vuelos de la app (a una región, a una nota, a un grupo, la
 * entrada). El giro lento del globo no: ahí sí se notaría lo borroso.
 *
 * Cuidado con MapLibre: `setPixelRatio` redimensiona el lienzo y, si el mapa
 * está quieto, llama a `stop()` y avisa "terminó de moverse" (`moveend`). Eso
 * cortaba animaciones y adelantaba la ficha de la nota (20/10/2026). Por eso la
 * resolución baja *después* de que el vuelo arrancó: con el mapa en movimiento,
 * MapLibre solo redimensiona.
 *
 * No hace: no decide a dónde ni cuánto dura el vuelo (`motion.ts`, `framing.ts`).
 */

// Fracción de la resolución de la pantalla durante un vuelo: 0.8 × 1.25 = 1.0
// en la laptop de Benji, el punto medio de la medición de arriba.
export const FLIGHT_RESOLUTION_FACTOR = 0.8;

/** Lo que este módulo usa del mapa de MapLibre (así se prueba sin WebGL). */
export interface FlightMap {
  isMoving(): boolean;
  getPixelRatio(): number;
  setPixelRatio(pixelRatio: number): void;
  redraw(): unknown;
  once(type: 'moveend', listener: () => void): unknown;
}

/**
 * Resolución durante un vuelo.
 *
 * @param devicePixelRatio Resolución de la pantalla (`window.devicePixelRatio`).
 * @returns Resolución reducida, con dos decimales.
 */
export function flightPixelRatio(devicePixelRatio: number): number {
  return Math.round(devicePixelRatio * FLIGHT_RESOLUTION_FACTOR * 100) / 100;
}

/**
 * Crea la función que hace volar el mapa con menos resolución.
 *
 * Si un vuelo interrumpe a otro, solo el último devuelve la nitidez: así no
 * parpadea a media ruta. Al aterrizar se redibuja en el mismo cuadro en que
 * se cambia la resolución, para que no se vea un cuadro vacío.
 *
 * @param map Mapa de MapLibre.
 * @param screenRatio Lee la resolución de la pantalla en ese momento (cambia si
 *   la persona hace zoom en el navegador o mueve la ventana a otro monitor).
 * @returns `fly(duration, start)`: llama a `start` (que lanza `flyTo` o
 *   `easeTo`), baja la resolución si el mapa ya se mueve y la regresa al
 *   terminar. Con duración 0, o si el sistema pidió menos movimiento y MapLibre
 *   saltó sin animar, solo llama a `start`.
 *
 * @example
 *   const fly = smoothFlights(map, () => window.devicePixelRatio);
 *   fly(2400, () => map.flyTo({ center, zoom, duration: 2400 }));
 */
export function smoothFlights(
  map: FlightMap,
  screenRatio: () => number,
): (duration: number, start: () => void) => void {
  let latest = 0;
  // Devuelve la nitidez en el cuadro siguiente, si nadie despegó después.
  const restoreAfter = (flight: number) => {
    requestAnimationFrame(() => {
      const full = screenRatio();
      if (flight !== latest || map.getPixelRatio() === full) return;
      map.setPixelRatio(full);
      map.redraw();
    });
  };
  return (duration, start) => {
    if (duration <= 0) {
      start();
      return;
    }
    latest += 1;
    const flight = latest;
    start();
    if (!map.isMoving()) {
      // Saltó sin animar: si un vuelo anterior dejó la resolución baja, vuelve.
      restoreAfter(flight);
      return;
    }
    const low = flightPixelRatio(screenRatio());
    if (map.getPixelRatio() !== low) map.setPixelRatio(low);
    // `moveend` llega dentro del cuadro de MapLibre: se espera al siguiente para
    // cambiar el lienzo y dibujarlo de inmediato.
    map.once('moveend', () => {
      restoreAfter(flight);
    });
  };
}
