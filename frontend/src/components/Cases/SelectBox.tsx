/**
 * Casilla para elegir un elemento o un grupo completo (F12, ADR-0107).
 *
 * La de un grupo puede quedar «a medias» (`some`): el navegador la dibuja con
 * una raya, que solo se puede poner desde JavaScript (`indeterminate`).
 *
 * No hace: no guarda la selección (avisa con `onChange`).
 */
import type { SelectionState } from './selection';

interface SelectBoxProps {
  state: SelectionState;
  onChange: (checked: boolean) => void;
  /** Para el lector de pantalla: «Elegir a Juan», «Elegir todas las personas». */
  label: string;
  disabled?: boolean;
}

export function SelectBox({ state, onChange, label, disabled = false }: SelectBoxProps) {
  return (
    <input
      type="checkbox"
      aria-label={label}
      checked={state === 'all'}
      disabled={disabled}
      ref={(element) => {
        if (element) element.indeterminate = state === 'some';
      }}
      onChange={(event) => {
        onChange(event.target.checked);
      }}
      className="size-4 shrink-0 cursor-pointer accent-sky-400 disabled:cursor-default"
    />
  );
}
