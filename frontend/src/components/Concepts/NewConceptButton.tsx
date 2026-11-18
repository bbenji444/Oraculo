/**
 * «+ Nuevo concepto» sin salir de Explorar (ADR-0109).
 *
 * El mismo formulario de la pantalla Conceptos, en una ventana: se escribe lo
 * que se quiere seguir, la IA propone las frases y, al guardar, el concepto
 * queda elegido para la búsqueda. Solo lo ve un superusuario (ADR-0042), igual
 * que el botón de la pantalla Conceptos.
 *
 * No hace: no busca; deja el concepto elegido en `useExplorerStore`.
 */
import { useState } from 'react';

import { useMe } from '../../hooks/useAuth';
import { useExplorerStore } from '../../store/explorer';
import { Modal } from '../Deliveries/Modal';
import { ConceptForm } from './ConceptForm';

interface NewConceptButtonProps {
  /** Clases del botón, para que se vea como los demás de donde se ponga. */
  className: string;
}

export function NewConceptButton({ className }: NewConceptButtonProps) {
  const canCreate = useMe().data?.role === 'superuser';
  const [open, setOpen] = useState(false);
  const conceptIds = useExplorerStore((s) => s.conceptIds);
  const toggle = useExplorerStore((s) => s.toggleConcept);
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
              if (!conceptIds.includes(concept.id)) toggle(concept.id);
              close();
            }}
          />
        </Modal>
      )}
    </>
  );
}
