/**
 * Caja de "chips" para palabras clave o exclusiones.
 *
 * Enter o coma agregan lo escrito; pegar una lista separada por comas o
 * renglones agrega varias de una vez; Retroceso con la caja vacía quita la
 * última. Cada chip avisa si el backend lo rechazaría (comillas, OR...).
 *
 * Diseño «consola táctica» (ADR-0036): la caja se enciende al escribir y cada
 * chip entra con un pequeño salto y brilla al pasar el mouse.
 */
import { useId, useState } from 'react';

import { addTerms, termWarning } from './terms';

interface KeywordChipsProps {
  label: string;
  hint: string;
  terms: string[];
  onChange: (terms: string[]) => void;
  /** Mensajes del backend para este campo. */
  errors?: string[];
  /** Exclusiones se pintan en rojo para distinguirlas de un vistazo. */
  tone: 'keyword' | 'exclude';
}

const TONES = {
  keyword:
    'border-sky-400/35 bg-sky-400/10 text-sky-100 hover:shadow-[0_0_12px_rgb(0_210_255/0.35)]',
  exclude:
    'border-rose-400/35 bg-rose-500/10 text-rose-100 hover:shadow-[0_0_12px_rgb(255_77_109/0.35)]',
};

export function KeywordChips({ label, hint, terms, onChange, errors, tone }: KeywordChipsProps) {
  const [text, setText] = useState('');
  const id = useId();
  const hasErrors = errors !== undefined && errors.length > 0;

  function commit(value: string) {
    if (value.trim() === '') return;
    onChange(addTerms(terms, value));
    setText('');
  }

  return (
    <div>
      <label htmlFor={id} className="hud-label">
        {label}
      </label>
      <div
        className={`hud-input flex flex-wrap gap-1.5 p-2 ${hasErrors ? 'border-rose-500/70' : ''}`}
      >
        {terms.map((term) => {
          const warning = termWarning(term);
          return (
            <span
              key={term}
              title={warning ?? undefined}
              className={`hud-reveal inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-xs transition-shadow duration-300 ${
                warning ? 'border-amber-400/60 bg-amber-400/10 text-amber-100' : TONES[tone]
              }`}
            >
              {tone === 'exclude' && <span aria-hidden="true">−</span>}
              {term}
              <button
                type="button"
                aria-label={`Quitar "${term}"`}
                onClick={() => {
                  onChange(terms.filter((t) => t !== term));
                }}
                className="ml-0.5 rounded text-slate-400 hover:text-slate-100 focus-visible:outline-2 focus-visible:outline-sky-400"
              >
                ×
              </button>
            </span>
          );
        })}
        <input
          id={id}
          value={text}
          aria-invalid={hasErrors}
          aria-describedby={`${id}-hint`}
          placeholder={terms.length === 0 ? 'Escribe y presiona Enter…' : ''}
          onChange={(event) => {
            const value = event.target.value;
            // Una coma escrita cierra el chip, igual que Enter.
            if (value.includes(',')) commit(value);
            else setText(value);
          }}
          onKeyDown={(event) => {
            if (event.key === 'Enter') {
              event.preventDefault();
              commit(text);
            } else if (event.key === 'Backspace' && text === '' && terms.length > 0) {
              onChange(terms.slice(0, -1));
            }
          }}
          onPaste={(event) => {
            const pasted = event.clipboardData.getData('text');
            if (/[,\n]/.test(pasted)) {
              event.preventDefault();
              commit(`${text}${pasted}`);
            }
          }}
          onBlur={() => {
            commit(text);
          }}
          className="min-w-[10rem] flex-1 bg-transparent px-1 py-0.5 text-sm text-slate-100 placeholder:text-slate-600 focus:outline-none"
        />
      </div>
      <p id={`${id}-hint`} className="mt-1 text-xs text-slate-500">
        {hint}
      </p>
      {errors?.map((message) => (
        <p key={message} className="mt-1 text-xs text-rose-300">
          {message}
        </p>
      ))}
    </div>
  );
}
