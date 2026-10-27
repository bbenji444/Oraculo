/**
 * La hora actual, que se renueva cada cierto tiempo (27/10/2026). La usan
 * los relojes y cronómetros del Centro de mando.
 *
 * Conviene usarla en un componente pequeño: el que la usa se vuelve a
 * dibujar en cada tic.
 */
import { useEffect, useState } from 'react';

// Un tic por segundo: lo que cambia un reloj con segundos.
const DEFAULT_TICK_MS = 1000;

/**
 * @param tickMs Cada cuántos milisegundos se renueva.
 * @returns La hora del último tic.
 */
export function useNow(tickMs: number = DEFAULT_TICK_MS): Date {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const timer = window.setInterval(() => {
      setNow(new Date());
    }, tickMs);
    return () => {
      window.clearInterval(timer);
    };
  }, [tickMs]);
  return now;
}
