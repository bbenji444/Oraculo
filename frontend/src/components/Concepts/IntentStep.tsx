/**
 * Primer paso de un concepto nuevo: «¿Qué noticias quieres seguir?» (ADR-0109).
 *
 * La persona lo escribe en sus palabras y la IA propone las frases. También
 * puede saltarse la IA y escribirlas a mano. Lo escrito se guarda como la
 * descripción del concepto, que es contra lo que la IA juzga cada nota.
 *
 * No hace: no llama a la IA (lo hace el formulario con `onPropose`).
 */
import { HudButton } from '../ui/HudButton';

interface IntentStepProps {
  /** Prefijo de ids del formulario. */
  id: string;
  value: string;
  onChange: (value: string) => void;
  onPropose: () => void;
  onSkip: () => void;
  pending: boolean;
  /** Mensajes del backend para la descripción (muy corta, por ejemplo). */
  errors?: string[];
  /** Otro error de la propuesta (la IA no respondió, falta su llave). */
  error: string | null;
}

// Igual que el máximo de la descripción en el backend (DESCRIPTION_MAX_LENGTH).
const MAX_LENGTH = 500;

export function IntentStep({
  id,
  value,
  onChange,
  onPropose,
  onSkip,
  pending,
  errors,
  error,
}: IntentStepProps) {
  const invalid = errors !== undefined && errors.length > 0;
  return (
    <div className="space-y-4">
      <div>
        <label htmlFor={`${id}-intent`} className="hud-label">
          ¿Qué noticias quieres seguir?
        </label>
        <textarea
          id={`${id}-intent`}
          value={value}
          maxLength={MAX_LENGTH}
          rows={3}
          aria-invalid={invalid}
          aria-describedby={`${id}-intent-hint`}
          placeholder="Por ejemplo: robo de autos y camionetas con violencia en Jalisco"
          onChange={(event) => {
            onChange(event.target.value);
          }}
          className={`hud-input ${invalid ? 'border-rose-500/70' : ''}`}
        />
        <p id={`${id}-intent-hint`} className="mt-1 text-xs text-slate-500">
          Escríbelo como se lo contarías a un colega. La IA propone las frases de búsqueda y tú las
          revisas antes de guardar.
        </p>
        {errors?.map((message) => (
          <p key={message} className="mt-1 text-xs text-rose-300">
            {message}
          </p>
        ))}
      </div>

      {error && (
        <p
          role="alert"
          className="rounded-lg border border-rose-500/30 bg-rose-500/10 px-3 py-2 text-sm text-rose-200"
        >
          {error}
        </p>
      )}

      <div className="flex flex-wrap items-center gap-2 border-t border-sky-400/10 pt-5">
        <HudButton variant="solid" disabled={pending || value.trim() === ''} onClick={onPropose}>
          {pending ? 'La IA está pensando…' : 'Proponer frases'}
        </HudButton>
        <HudButton variant="ghost" onClick={onSkip}>
          Prefiero escribirlas yo
        </HudButton>
      </div>
    </div>
  );
}
