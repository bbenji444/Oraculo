/**
 * Ventana al centro de la pantalla para la sección «Envíos» (mismo estilo que
 * el filtro del expediente). Se cierra con Esc, con «×» o con un clic en el
 * fondo oscuro.
 *
 * No hace: no decide su contenido.
 */
import { type ReactNode, useEffect, useId, useRef } from 'react';
import { createPortal } from 'react-dom';

import { GLASS } from '../Explore/ui';

interface ModalProps {
  title: string;
  onClose: () => void;
  children: ReactNode;
}

export function Modal({ title, onClose, children }: ModalProps) {
  const panelRef = useRef<HTMLDivElement>(null);
  const titleId = useId();

  useEffect(() => {
    panelRef.current?.focus();
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => {
      window.removeEventListener('keydown', onKey);
    };
  }, [onClose]);

  return createPortal(
    <div
      className="mando-modal-backdrop fixed inset-0 z-[60] flex items-center justify-center p-4"
      onPointerDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
        className={`${GLASS} mando-modal w-[30rem] max-w-full space-y-4 bg-[#06121a]/[0.98] p-5 outline-none`}
      >
        <div className="flex items-center justify-between">
          <h2 id={titleId} className="mando-kicker">
            {title}
          </h2>
          <button
            type="button"
            onClick={onClose}
            aria-label="Cerrar"
            className="hud-icon-btn size-7 text-sm"
          >
            ×
          </button>
        </div>
        {children}
      </div>
    </div>,
    document.body,
  );
}
