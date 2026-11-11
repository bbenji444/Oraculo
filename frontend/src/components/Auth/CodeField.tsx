/**
 * Campo del código de 6 dígitos de Microsoft Authenticator.
 *
 * Teclado numérico en el celular (`inputMode`), y `one-time-code` para que el
 * navegador ofrezca el código si lo tiene. Solo deja escribir números.
 *
 * No hace: no revisa el código (eso es del servidor).
 */
import { useId } from 'react';

interface CodeFieldProps {
  value: string;
  onChange: (value: string) => void;
}

export function CodeField({ value, onChange }: CodeFieldProps) {
  const id = useId();
  return (
    <div>
      <label htmlFor={id} className="hud-label">
        Código de 6 dígitos
      </label>
      <input
        id={id}
        value={value}
        inputMode="numeric"
        autoComplete="one-time-code"
        maxLength={7}
        placeholder="123456"
        autoFocus
        onChange={(e) => {
          onChange(e.target.value.replace(/[^\d ]/g, ''));
        }}
        className="hud-input text-center font-mono text-xl tracking-[0.4em]"
      />
    </div>
  );
}
