/**
 * «Mi contraseña»: cambiar la contraseña con la sesión abierta (ADR-0043).
 *
 * Pide la actual y la nueva dos veces. Al guardar, el servidor cierra las
 * demás sesiones de la persona (por si alguien más la conocía) y deja abierta
 * la de este navegador.
 *
 * No hace: no valida las reglas por sí mismo (las dice el servidor).
 */
import { useState } from 'react';

import { useChangePassword } from '../../hooks/useAuth';
import { Modal } from '../Deliveries/Modal';
import { HudButton } from '../ui/HudButton';
import { PasswordField } from './PasswordField';

export function ChangePasswordDialog({ onClose }: { onClose: () => void }) {
  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');
  const [repeat, setRepeat] = useState('');
  const change = useChangePassword();
  const mismatch = repeat !== '' && repeat !== next;

  return (
    <Modal title="Cambiar mi contraseña" onClose={onClose}>
      {change.isSuccess ? (
        <div className="space-y-3">
          <p className="text-sm text-emerald-300">
            Listo. Si tenías el monitor abierto en otra computadora, ahí tendrás que volver a
            entrar.
          </p>
          <HudButton size="sm" variant="solid" onClick={onClose}>
            Cerrar
          </HudButton>
        </div>
      ) : (
        <form
          className="space-y-3"
          onSubmit={(event) => {
            event.preventDefault();
            if (!current || !next || next !== repeat) return;
            change.mutate(
              { current, next },
              {
                // El servidor ya dejó la cookie de la sesión nueva: es la misma
                // persona, así que la pantalla sigue tal cual.
                onSuccess: () => {
                  setCurrent('');
                  setNext('');
                  setRepeat('');
                },
              },
            );
          }}
        >
          <PasswordField
            label="Contraseña actual"
            value={current}
            onChange={setCurrent}
            autoComplete="current-password"
            autoFocus
          />
          <PasswordField
            label="Contraseña nueva"
            value={next}
            onChange={setNext}
            autoComplete="new-password"
          />
          <PasswordField
            label="Repite la nueva"
            value={repeat}
            onChange={setRepeat}
            autoComplete="new-password"
          />
          <p className="text-xs text-slate-500">
            Al menos 12 caracteres, con letras y números, sin tu usuario.
          </p>
          {mismatch && <p className="text-xs text-amber-300">Las contraseñas no coinciden.</p>}
          {change.error && (
            <p role="alert" className="text-sm text-rose-300">
              {change.error.message}
            </p>
          )}
          <HudButton
            type="submit"
            size="sm"
            variant="solid"
            disabled={!current || !next || next !== repeat || change.isPending}
          >
            {change.isPending ? 'Guardando…' : 'Guardar'}
          </HudButton>
        </form>
      )}
    </Modal>
  );
}
