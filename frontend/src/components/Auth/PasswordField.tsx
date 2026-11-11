/**
 * Campo de contraseña con botón «Ver / Ocultar».
 *
 * `autoComplete` permite que el gestor de contraseñas del navegador la guarde
 * (`current-password`) o proponga una nueva (`new-password`).
 *
 * No hace: no valida la contraseña.
 */
import { useId, useState } from 'react';

import { HudButton } from '../ui/HudButton';

interface PasswordFieldProps {
  label: string;
  value: string;
  onChange: (value: string) => void;
  autoComplete: 'current-password' | 'new-password';
  autoFocus?: boolean;
}

export function PasswordField({
  label,
  value,
  onChange,
  autoComplete,
  autoFocus = false,
}: PasswordFieldProps) {
  const [visible, setVisible] = useState(false);
  const id = useId();
  return (
    <div>
      <label htmlFor={id} className="hud-label">
        {label}
      </label>
      <div className="flex gap-2">
        <input
          id={id}
          type={visible ? 'text' : 'password'}
          value={value}
          autoComplete={autoComplete}
          autoFocus={autoFocus}
          maxLength={128}
          onChange={(e) => {
            onChange(e.target.value);
          }}
          className="hud-input min-w-0 flex-1"
        />
        <HudButton
          size="sm"
          variant="ghost"
          aria-pressed={visible}
          aria-label={visible ? `Ocultar ${label.toLowerCase()}` : `Ver ${label.toLowerCase()}`}
          onClick={() => {
            setVisible((v) => !v);
          }}
        >
          {visible ? 'Ocultar' : 'Ver'}
        </HudButton>
      </div>
    </div>
  );
}
