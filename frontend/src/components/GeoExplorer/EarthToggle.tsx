/**
 * Botón para ver la Tierra de noche (con las ciudades iluminadas) o de día
 * (ADR-0017).
 */
import type { EarthMode } from '../../map/style';
import { Icon } from '../ui/Icon';

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
      className="hud-btn hud-btn--sm bg-[#050d12]/90"
    >
      <Icon name={night ? 'light_mode' : 'dark_mode'} className="text-amber-300" />
      {night ? 'Ver de día' : 'Ver de noche'}
    </button>
  );
}
