/**
 * Botón para pausar o reanudar el giro del globo (especificación §14.2:
 * "la rotación se detiene al interactuar y hay un botón para reanudarla").
 */
interface SpinToggleProps {
  spinning: boolean;
  onToggle: () => void;
}

export function SpinToggle({ spinning, onToggle }: SpinToggleProps) {
  return (
    <button
      type="button"
      aria-pressed={spinning}
      onClick={onToggle}
      className="flex items-center gap-2 rounded-xl border border-slate-700/80 bg-slate-900/85 px-3 py-2 text-xs text-slate-200 shadow-lg shadow-black/30 backdrop-blur hover:bg-slate-800 focus-visible:outline-2 focus-visible:outline-sky-400"
    >
      <svg aria-hidden="true" viewBox="0 0 20 20" className="size-4 fill-current text-sky-400">
        {spinning ? (
          <path d="M6 4h3v12H6zM11 4h3v12h-3z" />
        ) : (
          <path d="M10 3a7 7 0 1 1-6.32 4H2l3-4 3 4H5.9A5 5 0 1 0 10 5V3Z" />
        )}
      </svg>
      {spinning ? 'Pausar giro' : 'Girar globo'}
    </button>
  );
}
