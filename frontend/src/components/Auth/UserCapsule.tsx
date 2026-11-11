/**
 * La cápsula de la sesión en el encabezado: quién entró, «Mi contraseña» y
 * «Salir» (Benji, 11/11/2026: «que se vea más pro», como la barra de Oráculo).
 *
 * Una sola pieza redondeada con tres partes separadas por líneas finas:
 * - el ícono de persona y el nombre en mayúsculas;
 * - una llave que abre «Mi contraseña»;
 * - el botón de apagado, en rojo, que cierra la sesión.
 *
 * Los botones son solo ícono: su nombre (para lectores de pantalla y al pasar
 * el mouse) es «Mi contraseña» y «Salir».
 *
 * En modo desarrollo (sin sesión real) solo se ve el nombre.
 *
 * No hace: no cambia la contraseña (eso es `ChangePasswordDialog`).
 */
import { useState } from 'react';

import { useLogout } from '../../hooks/useAuth';
import type { Me } from '../../services/auth';
import { ChangePasswordDialog } from './ChangePasswordDialog';

function PersonIcon() {
  return (
    <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true" fill="currentColor">
      <path d="M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20Zm0 4.2a3.3 3.3 0 1 1 0 6.6 3.3 3.3 0 0 1 0-6.6Zm0 13.6a7.6 7.6 0 0 1-5.9-2.8c.9-1.6 3.3-2.6 5.9-2.6s5 1 5.9 2.6a7.6 7.6 0 0 1-5.9 2.8Z" />
    </svg>
  );
}

function KeyIcon() {
  return (
    <svg
      viewBox="0 0 24 24"
      width="16"
      height="16"
      aria-hidden="true"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <circle cx="7.5" cy="15.5" r="4.5" />
      <path d="m10.7 12.3 9.3-9.3M16 7l3 3M14 9l2 2" />
    </svg>
  );
}

function PowerIcon() {
  return (
    <svg
      viewBox="0 0 24 24"
      width="16"
      height="16"
      aria-hidden="true"
      fill="none"
      stroke="currentColor"
      strokeWidth="2.2"
      strokeLinecap="round"
    >
      <path d="M12 3v8" />
      <path d="M6.3 6.8a8 8 0 1 0 11.4 0" />
    </svg>
  );
}

export function UserCapsule({ me }: { me: Me }) {
  const logout = useLogout();
  const [changing, setChanging] = useState(false);
  const withSession = me.auth_mode === 'keys';

  return (
    <div className="user-capsule" role="group" aria-label="Tu sesión">
      <span className="user-capsule__who" title={`${me.display_name} (${me.username})`}>
        <span className="user-capsule__avatar">
          <PersonIcon />
        </span>
        <span className="user-capsule__name">{me.display_name}</span>
      </span>
      {withSession && (
        <>
          <span className="user-capsule__divider" aria-hidden="true" />
          <button
            type="button"
            className="user-capsule__action"
            aria-label="Mi contraseña"
            title="Mi contraseña"
            onClick={() => {
              setChanging(true);
            }}
          >
            <KeyIcon />
          </button>
          <span className="user-capsule__divider" aria-hidden="true" />
          <button
            type="button"
            className="user-capsule__power"
            aria-label="Salir"
            title="Salir"
            disabled={logout.isPending}
            onClick={() => {
              logout.mutate();
            }}
          >
            <PowerIcon />
          </button>
        </>
      )}
      {changing && (
        <ChangePasswordDialog
          onClose={() => {
            setChanging(false);
          }}
        />
      )}
    </div>
  );
}
