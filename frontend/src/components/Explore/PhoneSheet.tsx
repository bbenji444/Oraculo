/**
 * Hoja que sube desde abajo en el celular, para la ficha de una noticia o la
 * lista de notas de un lugar (Benji, 11/11/2026: «cuando ves una noticia se ve
 * feo»).
 *
 * En el celular la ficha flotante del globo quedaba encima de los paneles,
 * transparente y encimada. Aquí va sola, opaca, a todo lo ancho, con su
 * propio desplazamiento, y detrás un velo que la cierra al tocarlo.
 *
 * Se dibuja en `document.body` (portal): así queda encima de todo, aunque el
 * globo o los paneles tengan su propio apilamiento.
 *
 * No hace: no decide qué noticia se ve; muestra lo que le pasan.
 */
import { type ReactNode, useEffect } from 'react';
import { createPortal } from 'react-dom';

interface PhoneSheetProps {
  /** Nombre de la hoja para el lector de pantalla. */
  label: string;
  onClose: () => void;
  children: ReactNode;
}

export function PhoneSheet({ label, onClose, children }: PhoneSheetProps) {
  // Escape también la cierra (teclados externos y lectores de pantalla).
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => {
      window.removeEventListener('keydown', onKey);
    };
  }, [onClose]);

  return createPortal(
    <div className="hoja-celular fixed inset-0 z-[60] flex flex-col justify-end">
      <button
        type="button"
        aria-label="Cerrar"
        className="hoja-celular__velo absolute inset-0"
        onClick={onClose}
      />
      <div
        role="dialog"
        aria-label={label}
        className="hoja-celular__cuerpo relative max-h-[82dvh] overflow-y-auto overscroll-contain px-4 pt-3 pb-[max(1rem,env(safe-area-inset-bottom))]"
      >
        <span aria-hidden="true" className="hoja-celular__asa" />
        {children}
      </div>
    </div>,
    document.body,
  );
}
