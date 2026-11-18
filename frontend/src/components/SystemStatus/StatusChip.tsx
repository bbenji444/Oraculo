/**
 * Chip «Estado del sistema» abajo al centro, como el pie de Oráculo core
 * (ADR-0108): un piloto de color y una frase. Verde si todo funciona, ámbar si
 * algún servicio falla, rojo si no hay respuesta de la API.
 *
 * Usa el mismo `/health` que la pestaña Estado del sistema (`useHealth`), que
 * no pide sesión. Para quien puede ver esa pestaña, el chip lleva a ella. Qué
 * dice en cada caso está en `chipState.ts`.
 *
 * No hace: no se muestra en Explorar (ahí esa franja es de la consulta; lo
 * decide `App`).
 */
import { useHealth } from '../../hooks/useHealth';
import { statusChipOf } from './chipState';

interface StatusChipProps {
  /** Si la persona puede abrir la pestaña Estado del sistema. */
  linkToStatus: boolean;
}

export function StatusChip({ linkToStatus }: StatusChipProps) {
  const { state, label } = statusChipOf(useHealth());
  const content = (
    <>
      <span aria-hidden="true" className="hud-dot" />
      <span>{label}</span>
    </>
  );
  return linkToStatus ? (
    <a href="#/estado" className="hud-status-chip" data-state={state}>
      {content}
    </a>
  ) : (
    <p className="hud-status-chip" data-state={state}>
      {content}
    </p>
  );
}
