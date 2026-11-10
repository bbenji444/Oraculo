/**
 * Pantalla «Entrar con tu llave de Oráculo» (ADR-0042).
 *
 * La persona pega su llave `orc_live_…` (como la de la API de ChatGPT o de
 * Claude). El campo es de tipo contraseña (no se ve por encima del hombro),
 * no se autocompleta y se vacía al entrar: la llave no se guarda en el
 * navegador; la sesión vive en una cookie que el JavaScript no puede leer.
 *
 * No hace: no revisa la llave (eso es del servidor).
 */
import { useId, useState } from 'react';

import { useLogin } from '../../hooks/useAuth';
import { looksLikeKey } from '../../services/auth';
import { HudButton } from '../ui/HudButton';
import { HudPanel } from '../ui/HudPanel';

export function LoginScreen() {
  const [key, setKey] = useState('');
  const [visible, setVisible] = useState(false);
  const login = useLogin();
  const id = useId();
  const wellFormed = looksLikeKey(key);
  const showFormatHint = key.trim() !== '' && !wellFormed;

  return (
    <div className="relative z-10 flex h-full items-center justify-center px-4">
      <HudPanel scan className="w-full max-w-md space-y-5 px-6 py-7">
        <div>
          <p className="mando-kicker">Oráculo · Monitor de Noticias</p>
          <h1 className="mt-2 text-xl font-semibold text-slate-50">Entrar con tu llave</h1>
          <p className="mt-2 text-sm text-slate-400">
            Pega la llave de acceso que te dio el administrador. Empieza con{' '}
            <code className="text-sky-300">orc_live_</code>.
          </p>
        </div>
        <form
          className="space-y-3"
          onSubmit={(event) => {
            event.preventDefault();
            if (!wellFormed) return;
            login.mutate(key.trim(), {
              onSuccess: () => {
                setKey('');
              },
            });
          }}
        >
          <label htmlFor={`${id}-key`} className="hud-label">
            Llave de acceso
          </label>
          <div className="flex gap-2">
            <input
              id={`${id}-key`}
              type={visible ? 'text' : 'password'}
              value={key}
              autoComplete="off"
              autoCapitalize="off"
              spellCheck={false}
              maxLength={200}
              placeholder="orc_live_…"
              onChange={(e) => {
                setKey(e.target.value);
              }}
              className="hud-input min-w-0 flex-1 font-mono"
              aria-describedby={`${id}-help`}
            />
            <HudButton
              size="sm"
              variant="ghost"
              aria-pressed={visible}
              onClick={() => {
                setVisible((v) => !v);
              }}
            >
              {visible ? 'Ocultar' : 'Ver'}
            </HudButton>
          </div>
          <p id={`${id}-help`} className="text-xs text-slate-500">
            {showFormatHint
              ? 'Así no se ve una llave: revisa que la copiaste completa (58 caracteres).'
              : 'Tu sesión dura hasta 8 horas y se cierra sola tras 1 hora sin uso.'}
          </p>
          {login.error && (
            <p role="alert" className="text-sm text-rose-300">
              {login.error.message}
            </p>
          )}
          <HudButton
            type="submit"
            variant="solid"
            className="w-full justify-center"
            disabled={!wellFormed || login.isPending}
          >
            {login.isPending ? 'Revisando…' : 'Entrar'}
          </HudButton>
        </form>
        <p className="text-xs text-slate-500">
          ¿No tienes llave o la perdiste? Pídele una nueva al administrador. Nunca la compartas ni
          la pegues en chats o correos.
        </p>
      </HudPanel>
    </div>
  );
}
