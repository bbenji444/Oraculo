/**
 * El punto de donde sale la onda del clic en los botones (27/10/2026,
 * styles/hud.css).
 *
 * Un solo oyente para toda la página: al mover el mouse sobre un `.hud-btn`,
 * pone en ese elemento las variables CSS `--mx` y `--my` (la posición del
 * cursor dentro de él). El CSS dibuja con ellas la onda del clic. Así no hay un
 * oyente por componente ni se vuelve a dibujar React: solo cambia una variable,
 * una vez por cuadro.
 *
 * Hasta el 17/11/2026 también encendía un halo en los paneles. Se quitó al
 * darles la forma de las tarjetas de Oráculo core, que no lo tienen (ADR-0108).
 *
 * No hace: no dibuja nada ni decide estilos.
 */

const TARGETS = '.hud-btn';

/** Posición del punto dentro de un rectángulo, en píxeles. */
export function pointIn(
  rect: Pick<DOMRect, 'left' | 'top'>,
  clientX: number,
  clientY: number,
): { x: number; y: number } {
  return { x: clientX - rect.left, y: clientY - rect.top };
}

/**
 * Empieza a seguir al mouse.
 *
 * @returns Una función que deja de seguirlo.
 */
export function installSpotlight(root: Document = document): () => void {
  let frame = 0;
  let last: PointerEvent | null = null;

  const apply = () => {
    frame = 0;
    if (!last || !(last.target instanceof Element)) return;
    const target = last.target.closest<HTMLElement>(TARGETS);
    if (!target) return;
    const { x, y } = pointIn(target.getBoundingClientRect(), last.clientX, last.clientY);
    target.style.setProperty('--mx', `${String(x)}px`);
    target.style.setProperty('--my', `${String(y)}px`);
  };

  const onMove = (event: PointerEvent) => {
    last = event;
    // Una vez por cuadro: el mouse avisa más veces de las que se dibuja.
    if (!frame) frame = requestAnimationFrame(apply);
  };

  root.addEventListener('pointermove', onMove, { passive: true });
  // Al presionar también: la onda del clic sale de donde está el dedo.
  root.addEventListener('pointerdown', onMove, { passive: true });
  return () => {
    root.removeEventListener('pointermove', onMove);
    root.removeEventListener('pointerdown', onMove);
    if (frame) cancelAnimationFrame(frame);
  };
}
