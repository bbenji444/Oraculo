/**
 * La cápsula de la sesión en el encabezado: quién entró, «Mi contraseña» y
 * «Salir» (Benji, 11/11/2026: «que se vea más pro», como la barra de Oráculo).
 *
 * Una sola pieza redondeada con tres partes separadas por líneas finas:
 * - el ícono de persona y el nombre en mayúsculas;
 * - una llave que abre «Mi contraseña»;
 * - el botón de apagado, en rojo, que cierra la sesión.
 *
 * Los botones son solo ícono (Material Icons, como en Oráculo, ADR-0108): su
 * nombre (para lectores de pantalla y al pasar el mouse) es «Mi contraseña» y
 * «Salir».
 *
 * En modo desarrollo (sin sesión real) solo se ve el nombre. Tampoco hay
 * botones si se entró por el gateway de Oráculo (ADR-0119): la sesión y la
 * contraseña son las de Oráculo, no las del monitor.
 *
 * No hace: no cambia la contraseña (eso es `ChangePasswordDialog`).
 */
import { useState } from 'react';

import { useAppConfig } from '../../hooks/useAppConfig';
import { useLogout } from '../../hooks/useAuth';
import type { Me } from '../../services/auth';
import { Icon } from '../ui/Icon';
import { ChangePasswordDialog } from './ChangePasswordDialog';

export function UserCapsule({ me }: { me: Me }) {
  const logout = useLogout();
  const [changing, setChanging] = useState(false);
  const config = useAppConfig();
  // Mientras no se sabe, sin botones: así no aparecen y desaparecen al entrar
  // por Oráculo. Si la configuración falla, se muestran (acceso directo).
  const viaGateway = config.data?.via_gateway ?? config.isPending;
  // Sin entrada con contraseña no hay «Mi contraseña» ni «Salir» (ADR-0121).
  const withSession =
    me.auth_mode === 'keys' && !viaGateway && config.data?.password_login === true;

  return (
    <div className="user-capsule" role="group" aria-label="Tu sesión">
      <span className="user-capsule__who" title={`${me.display_name} (${me.username})`}>
        <span className="user-capsule__avatar">
          <Icon name="account_circle" className="text-xl" />
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
            <Icon name="key" className="text-lg" />
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
            <Icon name="power_settings_new" className="text-lg" />
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
