/**
 * «+ Nuevo concepto» sin salir de Explorar (ADR-0109).
 *
 * El mismo formulario de la pantalla Conceptos, en una ventana: se escribe lo
 * que se quiere seguir, la IA propone las frases y, al guardar, el concepto
 * queda elegido para la búsqueda. Solo lo ve un superusuario (ADR-0042), igual
 * que el botón de la pantalla Conceptos. Va en el panel del diseño clásico y
 * en la ventana «¿Qué rastrear?» del Centro de mando.
 *
 * No hace: no busca; deja el concepto elegido en `useExplorerStore` (o se lo
 * pasa a `onCreated`, si quien lo usa decide cómo elegirlo).
 */
import { useEffect, useState } from 'react';

import { useMe } from '../../hooks/useAuth';
import type { Concept } from '../../services/concepts';
import { useExplorerStore } from '../../store/explorer';
import { Modal } from '../Deliveries/Modal';
import { ConceptForm } from './ConceptForm';

interface NewConceptButtonProps {
  /** Clases del botón, para que se vea como los demás de donde se ponga. */
  className: string;
  /**
   * Qué hacer con el concepto recién guardado. Sin esto, se agrega a los
   * conceptos elegidos de la búsqueda.
   */
  onCreated?: (concept: Concept) => void;
}

export function NewConceptButton({ className, onCreated }: NewConceptButtonProps) {
  const canCreate = useMe().data?.role === 'superuser';
  const [open, setOpen] = useState(false);
  const conceptIds = useExplorerStore((s) => s.conceptIds);
  const toggle = useExplorerStore((s) => s.toggleConcept);

  useEffect(() => {
    if (!open) return;
    // La ventana puede abrirse encima de otra («¿Qué rastrear?»), que también
    // se cierra con Esc. Se escucha antes que nadie (fase de captura) para que
    // Esc cierre solo esta.
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') return;
      event.stopPropagation();
      setOpen(false);
    };
    window.addEventListener('keydown', onKey, true);
    return () => {
      window.removeEventListener('keydown', onKey, true);
    };
  }, [open]);

  if (!canCreate) return null;
  const close = () => {
    setOpen(false);
  };
  return (
    <>
      <button
        type="button"
        onClick={() => {
          setOpen(true);
        }}
        title="Escribe lo que quieres seguir y la IA propone las frases"
        className={className}
      >
        + Nuevo concepto
      </button>
      {open && (
        // La ventana ya se desplaza sola si el formulario no cabe (.mando-modal).
        <Modal title="Nuevo concepto" onClose={close}>
          <ConceptForm
            embedded
            onClose={close}
            onSaved={(concept) => {
              if (onCreated) onCreated(concept);
              else if (!conceptIds.includes(concept.id)) toggle(concept.id);
              close();
            }}
          />
        </Modal>
      )}
    </>
  );
}
