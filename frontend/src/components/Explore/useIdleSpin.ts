/**
 * El globo gira solo tras 5 minutos sin que nadie toque nada (Benji,
 * 11/11/2026: «si ya tenemos una búsqueda y estamos investigando algo, el
 * globo va a empezar a girar por sí solo, solo cuando estemos 5 minutos
 * ausentes»).
 *
 * - Cualquier movimiento del mouse, toque, rueda o tecla reinicia la cuenta.
 * - Si el giro lo prendió la ausencia, al volver se detiene, salvo en una
 *   consulta nueva (sin búsqueda ni región), donde el globo ya gira.
 * - Con «Menos movimiento» del sistema no hace nada.
 *
 * No hace: no mueve la cámara; solo prende o apaga `spinning` en el store.
 */
import { useEffect } from 'react';

import { useExplorerStore } from '../../store/explorer';

/** 5 minutos sin tocar nada (Benji, 11/11/2026). */
export const IDLE_SPIN_MS = 5 * 60 * 1000;
// Señales de que alguien está frente a la pantalla.
const ACTIVITY_EVENTS = ['pointerdown', 'pointermove', 'wheel', 'keydown', 'touchstart'] as const;

/** Si el globo debería girar solo por estar en una consulta nueva. */
function composingNewQuery(): boolean {
  const { searchId, regionId } = useExplorerStore.getState();
  return searchId === null && regionId === null;
}

/**
 * Prende el giro tras {@link IDLE_SPIN_MS} sin actividad, mientras Explorar
 * está a la vista.
 *
 * @param active Si Explorar está a la vista.
 */
export function useIdleSpin(active: boolean): void {
  useEffect(() => {
    if (!active) return;
    let timer = 0;
    let spunByIdle = false;
    const arm = () => {
      window.clearTimeout(timer);
      timer = window.setTimeout(() => {
        const store = useExplorerStore.getState();
        if (store.motion === 'off' || store.spinning) return;
        spunByIdle = true;
        store.setSpinning(true);
      }, IDLE_SPIN_MS);
    };
    const onActivity = () => {
      if (spunByIdle) {
        spunByIdle = false;
        if (!composingNewQuery()) useExplorerStore.getState().setSpinning(false);
      }
      arm();
    };
    for (const name of ACTIVITY_EVENTS) {
      window.addEventListener(name, onActivity, { passive: true });
    }
    arm();
    return () => {
      window.clearTimeout(timer);
      for (const name of ACTIVITY_EVENTS) window.removeEventListener(name, onActivity);
    };
  }, [active]);
}
