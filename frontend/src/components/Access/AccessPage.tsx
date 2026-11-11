/**
 * Pantalla «Accesos» (solo superusuarios, ADR-0042, ADR-0043 y ADR-0047):
 * quién puede entrar al monitor.
 *
 * - Arriba, el interruptor «Pedir código de Microsoft Authenticator al entrar»
 *   (`LoginSettings`): apagado, basta usuario y contraseña.
 * - Cada persona trae su **llave de API** (`ApiKeyRow`) para conectarla con
 *   el resto de Oráculo: ver, copiar o generar otra.
 *
 * - «+ Nueva persona» da de alta a alguien con una contraseña temporal, que
 *   se muestra una sola vez; al entrar la cambia y conecta su Authenticator.
 * - Cada persona muestra su rol, si está activa, si su contraseña es
 *   temporal, si ya conectó Microsoft Authenticator y si está bloqueada.
 * - «Editar» cambia nombre, correo, rol o la desactiva, y tiene la sección
 *   «Seguridad»: restablecer contraseña o reiniciar autenticador.
 * - «Llaves de sistema» son para otros programas (no para personas).
 *
 * No hace: no aplica reglas (el servidor impide, por ejemplo, quitarte tu
 * propio rol o dejar el sistema sin superusuario).
 */
import { type CSSProperties, useState } from 'react';

import {
  useAccessUsers,
  useAuthSettings,
  useCreateUser,
  useUpdateUser,
} from '../../hooks/useAccess';
import { useMe } from '../../hooks/useAuth';
import type { AccessUser } from '../../services/access';
import { Modal } from '../Deliveries/Modal';
import { formatMexicoCity } from '../Explore/format';
import { HudButton } from '../ui/HudButton';
import { HudChip } from '../ui/HudChip';
import { HudPanel } from '../ui/HudPanel';
import { SectionHeading } from '../ui/SectionHeading';
import { ApiKeyRow } from './ApiKeyRow';
import { LoginSettings } from './LoginSettings';
import { SecurityActions } from './SecurityActions';
import { TemporaryPasswordNotice } from './TemporaryPasswordNotice';
import { UserForm, type UserFormValues } from './UserForm';
import { UserKeys } from './UserKeys';

// Las entradas escalonadas se cortan aquí: una lista larga no debe tardar en aparecer.
const MAX_STAGGER = 12;

function UserItem({
  user,
  index,
  isSelf,
  open,
  onToggle,
  onEdit,
}: {
  user: AccessUser;
  index: number;
  isSelf: boolean;
  open: boolean;
  onToggle: () => void;
  onEdit: () => void;
}) {
  // «Sin Authenticator» solo importa si al entrar se pide el código.
  const totpRequired = useAuthSettings().data?.totp_required ?? false;
  return (
    <li className="hud-reveal" style={{ '--i': Math.min(index, MAX_STAGGER) } as CSSProperties}>
      <HudPanel className={`px-5 py-4 ${user.is_active ? '' : 'opacity-70'}`}>
        <div className="flex flex-wrap items-center gap-x-5 gap-y-3">
          <div className="min-w-0 flex-1 basis-60">
            <p className="font-medium text-slate-50">
              {user.display_name}
              {isSelf && <span className="ml-2 text-xs text-sky-300">(tú)</span>}
            </p>
            <p className="mt-0.5 font-mono text-xs text-slate-400">
              {user.username}
              {user.email ? ` · ${user.email}` : ''}
            </p>
            <p className="mt-0.5 text-[11px] text-slate-500">
              {user.last_seen_at
                ? `Última entrada: ${formatMexicoCity(user.last_seen_at)}`
                : 'Todavía no entra'}
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <HudChip tone={user.role === 'superuser' ? 'violet' : 'cyan'}>
              {user.role === 'superuser' ? 'Superusuario' : 'Usuario'}
            </HudChip>
            <HudChip tone={user.is_active ? 'green' : 'slate'} dot>
              {user.is_active ? 'Activa' : 'Desactivada'}
            </HudChip>
            {user.must_change_password && <HudChip tone="amber">Contraseña temporal</HudChip>}
            {totpRequired && !user.totp_enrolled && (
              <HudChip tone="slate">Sin Authenticator</HudChip>
            )}
            {user.locked_until && (
              <HudChip tone="rose">Bloqueada hasta {formatMexicoCity(user.locked_until)}</HudChip>
            )}
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <HudButton size="sm" variant="ghost" aria-expanded={open} onClick={onToggle}>
              {open ? 'Ocultar llaves' : `Llaves de sistema (${String(user.active_keys)})`}
            </HudButton>
            <HudButton size="sm" onClick={onEdit}>
              Editar
            </HudButton>
          </div>
        </div>
        <ApiKeyRow user={user} />
        {open && <UserKeys user={user} />}
      </HudPanel>
    </li>
  );
}

function toValues(user: AccessUser): UserFormValues {
  return {
    username: user.username,
    display_name: user.display_name,
    email: user.email ?? '',
    role: user.role,
    is_active: user.is_active,
  };
}

export function AccessPage() {
  const me = useMe().data;
  const users = useAccessUsers();
  const create = useCreateUser();
  const update = useUpdateUser();
  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState<AccessUser | null>(null);
  const [openId, setOpenId] = useState<number | null>(null);
  // La contraseña temporal recién creada: solo vive en este aviso.
  const [temporary, setTemporary] = useState<{
    password: string;
    owner: string;
    username: string;
  } | null>(null);
  const list = users.data ?? [];

  return (
    <div className="h-full overflow-y-auto px-4 py-8 sm:px-8">
      <div className="mx-auto max-w-5xl">
        <SectionHeading
          kicker="Solo superusuarios"
          title="Accesos"
          description="Quién puede entrar al monitor y la llave de API de cada persona, para conectarla con el resto de Oráculo."
          actions={
            <HudButton
              variant="solid"
              size="sm"
              onClick={() => {
                create.reset();
                setCreating(true);
              }}
            >
              + Nueva persona
            </HudButton>
          }
        />
        <LoginSettings />
        {users.isPending && <p className="mt-6 text-sm text-slate-400">Cargando…</p>}
        {users.error && <p className="mt-6 text-sm text-rose-300">{users.error.message}</p>}
        <ul className="mt-6 space-y-3">
          {list.map((user, index) => (
            <UserItem
              key={user.id}
              user={user}
              index={index}
              isSelf={user.username === me?.username}
              open={openId === user.id}
              onToggle={() => {
                setOpenId(openId === user.id ? null : user.id);
              }}
              onEdit={() => {
                update.reset();
                setEditing(user);
              }}
            />
          ))}
        </ul>
      </div>
      {creating && (
        <Modal
          title="Nueva persona"
          onClose={() => {
            setCreating(false);
          }}
        >
          <UserForm
            editing={false}
            pending={create.isPending}
            error={create.error}
            onCancel={() => {
              setCreating(false);
            }}
            onSubmit={(values) => {
              create.mutate(
                {
                  username: values.username,
                  display_name: values.display_name,
                  email: values.email.trim() || null,
                  role: values.role,
                },
                {
                  onSuccess: (created) => {
                    setCreating(false);
                    setTemporary({
                      password: created.temporary_password,
                      owner: created.user.display_name,
                      username: created.user.username,
                    });
                  },
                },
              );
            }}
          />
        </Modal>
      )}
      {editing && (
        <Modal
          title={`Editar a ${editing.display_name}`}
          onClose={() => {
            setEditing(null);
          }}
        >
          <UserForm
            editing
            isSelf={editing.username === me?.username}
            initial={toValues(editing)}
            pending={update.isPending}
            error={update.error}
            onCancel={() => {
              setEditing(null);
            }}
            onSubmit={(values) => {
              update.mutate(
                {
                  id: editing.id,
                  patch: {
                    display_name: values.display_name,
                    email: values.email.trim(),
                    role: values.role,
                    is_active: values.is_active,
                  },
                },
                {
                  onSuccess: () => {
                    setEditing(null);
                  },
                },
              );
            }}
          />
          <SecurityActions
            user={editing}
            isSelf={editing.username === me?.username}
            onDeleted={() => {
              setEditing(null);
            }}
            onTemporaryPassword={(password) => {
              setTemporary({
                password,
                owner: editing.display_name,
                username: editing.username,
              });
              setEditing(null);
            }}
          />
        </Modal>
      )}
      {temporary && (
        <TemporaryPasswordNotice
          password={temporary.password}
          owner={temporary.owner}
          username={temporary.username}
          onClose={() => {
            setTemporary(null);
          }}
        />
      )}
    </div>
  );
}
