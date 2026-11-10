/**
 * Formulario de una persona en «Accesos»: usuario, nombre, correo, rol y si
 * está activa. Sirve para dar de alta (con usuario) y para editar (sin
 * cambiar el usuario, que es el identificador de sus búsquedas y bitácora).
 *
 * No hace: no guarda; avisa con `onSubmit`.
 */
import { useId, useState } from 'react';

import type { Role } from '../../services/auth';
import { HudButton } from '../ui/HudButton';
import { HudSelect } from '../ui/HudSelect';
import { HudSwitch } from '../ui/HudSwitch';

export interface UserFormValues {
  username: string;
  display_name: string;
  email: string;
  role: Role;
  is_active: boolean;
}

interface UserFormProps {
  initial?: UserFormValues;
  /** Al editar, el usuario no se cambia. */
  editing: boolean;
  /** Si es la persona que está usando la pantalla (no puede quitarse el rol). */
  isSelf?: boolean;
  pending: boolean;
  error: Error | null;
  onSubmit: (values: UserFormValues) => void;
  onCancel: () => void;
}

const EMPTY: UserFormValues = {
  username: '',
  display_name: '',
  email: '',
  role: 'user',
  is_active: true,
};

const ROLES = [
  { value: 'user' as const, label: 'Usuario: Explorar, Casos, Conceptos, Historial' },
  { value: 'superuser' as const, label: 'Superusuario: todo, también Estado y Accesos' },
];

export function UserForm({
  initial = EMPTY,
  editing,
  isSelf = false,
  pending,
  error,
  onSubmit,
  onCancel,
}: UserFormProps) {
  const [values, setValues] = useState(initial);
  const id = useId();
  const set = <K extends keyof UserFormValues>(field: K, value: UserFormValues[K]) => {
    setValues((v) => ({ ...v, [field]: value }));
  };

  return (
    <form
      className="space-y-3"
      onSubmit={(event) => {
        event.preventDefault();
        onSubmit(values);
      }}
    >
      {!editing && (
        <div>
          <label htmlFor={`${id}-user`} className="hud-label">
            Usuario <span className="font-normal text-slate-500">(sin espacios: ana.lopez)</span>
          </label>
          <input
            id={`${id}-user`}
            value={values.username}
            maxLength={60}
            autoComplete="off"
            onChange={(e) => {
              set('username', e.target.value);
            }}
            className="hud-input"
            required
          />
        </div>
      )}
      <div>
        <label htmlFor={`${id}-name`} className="hud-label">
          Nombre para mostrar
        </label>
        <input
          id={`${id}-name`}
          value={values.display_name}
          maxLength={120}
          onChange={(e) => {
            set('display_name', e.target.value);
          }}
          className="hud-input"
          required
        />
      </div>
      <div>
        <label htmlFor={`${id}-email`} className="hud-label">
          Correo <span className="font-normal text-slate-500">(opcional)</span>
        </label>
        <input
          id={`${id}-email`}
          type="email"
          value={values.email}
          maxLength={254}
          onChange={(e) => {
            set('email', e.target.value);
          }}
          className="hud-input"
        />
      </div>
      <HudSelect
        label="Rol"
        value={values.role}
        options={ROLES}
        disabled={isSelf}
        onChange={(role) => {
          set('role', role);
        }}
      />
      {editing && (
        <div className="flex items-center justify-between gap-3">
          <span className="text-sm text-slate-200">
            Puede entrar{' '}
            <span className="text-xs text-slate-500">(apagado: sus llaves dejan de servir)</span>
          </span>
          <HudSwitch
            checked={values.is_active}
            disabled={isSelf}
            onChange={(active) => {
              set('is_active', active);
            }}
            label="Puede entrar"
          />
        </div>
      )}
      {isSelf && (
        <p className="text-xs text-slate-500">
          Es tu propio usuario: no puedes quitarte el rol ni desactivarte.
        </p>
      )}
      {error && (
        <p role="alert" className="text-xs text-rose-300">
          {error.message}
        </p>
      )}
      <div className="flex flex-wrap items-center gap-2">
        <HudButton type="submit" variant="solid" size="sm" disabled={pending}>
          {pending ? 'Guardando…' : editing ? 'Guardar' : 'Dar de alta'}
        </HudButton>
        <HudButton size="sm" variant="ghost" onClick={onCancel}>
          Cancelar
        </HudButton>
      </div>
    </form>
  );
}
