/**
 * Si la pantalla cumple una media query de CSS, y se entera cuando cambia
 * (27/10/2026). Lo usa Explorar para saber si hay lugar a un lado del globo.
 *
 * No hace: no mide elementos; solo la ventana.
 */
import { useCallback, useSyncExternalStore } from 'react';

// Sin matchMedia (pruebas en jsdom, navegadores viejos) no hay a qué escuchar.
function hasMatchMedia(): boolean {
  return typeof window.matchMedia === 'function';
}

/**
 * @param query Por ejemplo `'(min-width: 640px)'`.
 * @param fallback Qué responder si el navegador no tiene `matchMedia`.
 * @returns `true` si la ventana la cumple ahora.
 */
export function useMediaQuery(query: string, fallback = false): boolean {
  const subscribe = useCallback(
    (notify: () => void) => {
      if (!hasMatchMedia()) return () => undefined;
      const list = window.matchMedia(query);
      list.addEventListener('change', notify);
      return () => {
        list.removeEventListener('change', notify);
      };
    },
    [query],
  );
  return useSyncExternalStore(
    subscribe,
    () => (hasMatchMedia() ? window.matchMedia(query).matches : fallback),
    () => fallback,
  );
}
