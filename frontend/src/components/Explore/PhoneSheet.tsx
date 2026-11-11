/**
 * Hoja que sube desde abajo en el celular, para la ficha de una noticia o la
 * lista de notas de un lugar (Benji, 11/11/2026).
 *
 * - Ocupa poco más de la mitad de la pantalla: arriba se ve el globo volar al
 *   lugar de la noticia.
 * - Es un poco transparente, para que se adivine el globo detrás.
 * - Se cierra con la ✕, tocando el globo o **deslizándola hacia abajo**
 *   (desde el asa o cuando su contenido ya está hasta arriba).
 *
 * Se dibuja en `document.body` (portal): así queda encima de todo, aunque el
 * globo o los paneles tengan su propio apilamiento.
 *
 * No hace: no decide qué noticia se ve; muestra lo que le pasan.
 */
import { type ReactNode, useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';

// Cuánto hay que deslizar hacia abajo (px) para que la hoja se cierre al soltar.
const CLOSE_DRAG_PX = 90;

interface PhoneSheetProps {
  /** Nombre de la hoja para el lector de pantalla. */
  label: string;
  onClose: () => void;
  children: ReactNode;
}

export function PhoneSheet({ label, onClose, children }: PhoneSheetProps) {
  const bodyRef = useRef<HTMLDivElement>(null);
  const [drag, setDrag] = useState(0);
  const onCloseRef = useRef(onClose);
  useEffect(() => {
    onCloseRef.current = onClose;
  }, [onClose]);

  // Escape también la cierra (teclados externos y lectores de pantalla).
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onCloseRef.current();
    };
    window.addEventListener('keydown', onKey);
    return () => {
      window.removeEventListener('keydown', onKey);
    };
  }, []);

  // Deslizar hacia abajo para cerrar. Con eventos táctiles no pasivos: así se
  // frena el desplazamiento del navegador solo cuando el contenido ya está
  // hasta arriba y el dedo baja; en los demás casos el texto se desplaza.
  useEffect(() => {
    const body = bodyRef.current;
    if (!body) return;
    let startY: number | null = null;
    let current = 0;
    const onStart = (event: TouchEvent) => {
      const touch = event.touches[0];
      startY = touch ? touch.clientY : null;
      current = 0;
    };
    const onMove = (event: TouchEvent) => {
      const touch = event.touches[0];
      if (startY === null || !touch) return;
      const dy = touch.clientY - startY;
      if (body.scrollTop <= 0 && dy > 0) {
        event.preventDefault();
        current = dy;
        setDrag(dy);
      } else if (current !== 0) {
        current = 0;
        setDrag(0);
      }
    };
    const onEnd = () => {
      if (current > CLOSE_DRAG_PX) onCloseRef.current();
      else setDrag(0);
      startY = null;
      current = 0;
    };
    body.addEventListener('touchstart', onStart, { passive: true });
    body.addEventListener('touchmove', onMove, { passive: false });
    body.addEventListener('touchend', onEnd);
    body.addEventListener('touchcancel', onEnd);
    return () => {
      body.removeEventListener('touchstart', onStart);
      body.removeEventListener('touchmove', onMove);
      body.removeEventListener('touchend', onEnd);
      body.removeEventListener('touchcancel', onEnd);
    };
  }, []);

  return createPortal(
    <div className="hoja-celular fixed inset-0 z-[60] flex flex-col justify-end">
      <button
        type="button"
        aria-label="Cerrar"
        className="hoja-celular__velo absolute inset-0"
        onClick={onClose}
      />
      <div
        ref={bodyRef}
        role="dialog"
        aria-label={label}
        data-dragging={drag > 0 ? '' : undefined}
        className="hoja-celular__cuerpo relative max-h-[55dvh] overflow-y-auto overscroll-contain px-4 pt-2 pb-[max(1rem,env(safe-area-inset-bottom))]"
        style={drag > 0 ? { transform: `translateY(${String(drag)}px)` } : undefined}
      >
        <span aria-hidden="true" className="hoja-celular__asa" />
        {children}
      </div>
    </div>,
    document.body,
  );
}
