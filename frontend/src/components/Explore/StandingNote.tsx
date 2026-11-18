/**
 * Marca y razón de una nota que no es relevante del todo (ADR-0117): «Por
 * confirmar», «Cercana», «Descartada por la IA» o «Sin revisar», y en letra
 * chica por qué lo dijo la IA («Por qué no: habla de otro hacker»). También
 * el botón «Ver las N que descartó la IA» (`DiscardedToggle`).
 *
 * Benji pidió que «No relevantes» no fuera basura y que se entienda por qué
 * cada nota quedó fuera; la razón de la IA ya llegaba de la API, pero no se
 * veía en ningún lado.
 *
 * No hace: no decide la banda (eso es `relevance.ts`) ni aparece en las
 * relevantes.
 */
import { useExplorerStore } from '../../store/explorer';
import { discardedToggleLabel, type StandingNote } from './relevance';

// Ayuda del botón: por qué existen y por qué conviene revisarlas.
const DISCARDED_HINT =
  'La IA dijo que no son de lo que se buscó. Muchas veces solo leyó el título y se ' +
  'equivoca: se ven con la marca «Descartada por la IA» y su razón.';

interface DiscardedToggleProps {
  /** Cuántas descartó la IA (`discardedCount`); con 0 no hay botón. */
  count: number;
  className?: string;
}

/**
 * Botón discreto «Ver las N que descartó la IA» / «Ocultar…»: muestra en la
 * lista, la cronología y el globo las notas ajenas, que ni «Incluir las no
 * relevantes» suma (revisión del 18/11/2026: entre ellas caían las notas
 * correctas de «hacker Eternal»).
 *
 * @param props Cuántas son y clases extra.
 * @returns El botón, o nada si no hay descartadas.
 */
export function DiscardedToggle({ count, className = '' }: DiscardedToggleProps) {
  const open = useExplorerStore((s) => s.showDiscarded);
  const setOpen = useExplorerStore((s) => s.setShowDiscarded);
  const label = discardedToggleLabel(count, open);
  if (label === null) return null;
  return (
    <button
      type="button"
      aria-pressed={open}
      title={DISCARDED_HINT}
      onClick={() => {
        setOpen(!open);
      }}
      className={`discarded-toggle ${className}`}
    >
      {label}
    </button>
  );
}

interface StandingBadgeProps {
  note: StandingNote;
  /**
   * Ayuda al pasar el mouse; por defecto, qué quiere decir la marca. La
   * cronología pone ahí la razón de la IA, que no cabe en su renglón.
   */
  title?: string;
}

/** La marca corta, con su explicación al pasar el mouse. */
export function StandingBadge({ note, title }: StandingBadgeProps) {
  return (
    <span className="standing-badge" data-standing={note.standing} title={title ?? note.hint}>
      {note.badge}
    </span>
  );
}

interface StandingReasonProps {
  note: StandingNote;
  /** Un renglón cortado con «…» (la lista compacta); si no, hasta dos renglones. */
  truncate?: boolean;
  className?: string;
}

/** La razón de la IA en letra chica, o nada si no dio razón. */
export function StandingReason({ note, truncate = false, className = '' }: StandingReasonProps) {
  if (!note.reason) return null;
  return (
    <span
      className={`standing-reason ${truncate ? 'block truncate' : 'line-clamp-2'} ${className}`}
      title={note.reason}
    >
      {note.reason}
    </span>
  );
}
