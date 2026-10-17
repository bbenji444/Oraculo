/**
 * Botón para ver la Tierra de noche (con las ciudades iluminadas) o de día
 * (ADR-0017).
 */
import type { EarthMode } from '../../map/style';

interface EarthToggleProps {
  earth: EarthMode;
  onChange: (earth: EarthMode) => void;
}

export function EarthToggle({ earth, onChange }: EarthToggleProps) {
  const night = earth === 'night';
  return (
    <button
      type="button"
      aria-pressed={!night}
      onClick={() => {
        onChange(night ? 'day' : 'night');
      }}
      className="flex items-center gap-2 rounded-xl border border-slate-700/80 bg-slate-900/85 px-3 py-2 text-xs text-slate-200 shadow-lg shadow-black/30 backdrop-blur hover:bg-slate-800 focus-visible:outline-2 focus-visible:outline-sky-400"
    >
      <svg aria-hidden="true" viewBox="0 0 20 20" className="size-4 fill-current text-amber-300">
        {night ? (
          <path d="M10 2a1 1 0 0 1 1 1v1a1 1 0 1 1-2 0V3a1 1 0 0 1 1-1Zm0 5a3 3 0 1 1 0 6 3 3 0 0 1 0-6Zm7 2a1 1 0 1 1 0 2h-1a1 1 0 1 1 0-2h1ZM4 9a1 1 0 1 1 0 2H3a1 1 0 1 1 0-2h1Zm6 6a1 1 0 0 1 1 1v1a1 1 0 1 1-2 0v-1a1 1 0 0 1 1-1Z" />
        ) : (
          <path d="M8.5 2.5a7.5 7.5 0 1 0 9 9 6 6 0 0 1-9-9Z" />
        )}
      </svg>
      {night ? 'Ver de día' : 'Ver de noche'}
    </button>
  );
}
