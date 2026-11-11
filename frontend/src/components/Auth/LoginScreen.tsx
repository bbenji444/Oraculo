/**
 * Pantalla «Entrar» del monitor, igual que la de Oráculo (ADR-0043).
 *
 * Pasos:
 * 1. usuario y contraseña;
 * 2. solo la primera vez: cambiar la contraseña temporal y dar de alta
 *    Microsoft Authenticator con un QR;
 * 3. el código de 6 dígitos de la app.
 *
 * Al terminar, el servidor deja la sesión en una cookie que el JavaScript no
 * puede leer; la pantalla no guarda la contraseña ni el código.
 *
 * No hace: no revisa nada por sí misma (todo lo decide el servidor).
 */
import { useId, useState } from 'react';
import { useMutation } from '@tanstack/react-query';

import { useOpenSession } from '../../hooks/useAuth';
import {
  type LoginStep,
  type Me,
  confirmEnrollment,
  looksLikeCode,
  setFirstPassword,
  startLogin,
  submitCode,
} from '../../services/auth';
import { HudButton } from '../ui/HudButton';
import { HudPanel } from '../ui/HudPanel';
import { CodeField } from './CodeField';
import { EnrollStep } from './EnrollStep';
import { PasswordField } from './PasswordField';

const TITLES: Record<LoginStep['next'] | 'credentials', { title: string; help: string }> = {
  credentials: {
    title: 'Entrar',
    help: 'Usa el usuario y la contraseña que te dio el administrador.',
  },
  change_password: {
    title: 'Crea tu contraseña',
    help: 'Tu contraseña es temporal. Elige una propia: al menos 12 caracteres, con letras y números, sin tu usuario.',
  },
  enroll: {
    title: 'Conecta tu celular',
    help: 'Como en Oráculo, cada vez que entres te pediremos un código de Microsoft Authenticator.',
  },
  code: {
    title: 'Código de verificación',
    help: 'Abre Microsoft Authenticator y escribe los 6 dígitos de «Oráculo Monitor».',
  },
  done: {
    title: 'Entrando…',
    help: 'Listo.',
  },
};

function CredentialsStep({ onDone }: { onDone: (step: LoginStep) => void }) {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const id = useId();
  const login = useMutation({
    mutationFn: () => startLogin(username.trim(), password),
    onSuccess: (step) => {
      setPassword('');
      onDone(step);
    },
  });
  return (
    <form
      className="space-y-3"
      onSubmit={(event) => {
        event.preventDefault();
        if (username.trim() && password) login.mutate();
      }}
    >
      <div>
        <label htmlFor={`${id}-user`} className="hud-label">
          Usuario
        </label>
        <input
          id={`${id}-user`}
          value={username}
          autoComplete="username"
          autoCapitalize="off"
          spellCheck={false}
          autoFocus
          maxLength={60}
          onChange={(e) => {
            setUsername(e.target.value);
          }}
          className="hud-input"
        />
      </div>
      <PasswordField
        label="Contraseña"
        value={password}
        onChange={setPassword}
        autoComplete="current-password"
      />
      {login.error && (
        <p role="alert" className="text-sm text-rose-300">
          {login.error.message}
        </p>
      )}
      <HudButton
        type="submit"
        variant="solid"
        className="w-full justify-center"
        disabled={!username.trim() || !password || login.isPending}
      >
        {login.isPending ? 'Revisando…' : 'Continuar'}
      </HudButton>
    </form>
  );
}

function NewPasswordStep({ ticket, onDone }: { ticket: string; onDone: (s: LoginStep) => void }) {
  const [password, setPassword] = useState('');
  const [repeat, setRepeat] = useState('');
  const change = useMutation({
    mutationFn: () => setFirstPassword(ticket, password),
    onSuccess: onDone,
  });
  const mismatch = repeat !== '' && repeat !== password;
  return (
    <form
      className="space-y-3"
      onSubmit={(event) => {
        event.preventDefault();
        if (password && password === repeat) change.mutate();
      }}
    >
      <PasswordField
        label="Contraseña nueva"
        value={password}
        onChange={setPassword}
        autoComplete="new-password"
        autoFocus
      />
      <PasswordField
        label="Repítela"
        value={repeat}
        onChange={setRepeat}
        autoComplete="new-password"
      />
      {mismatch && <p className="text-xs text-amber-300">Las dos contraseñas no coinciden.</p>}
      {change.error && (
        <p role="alert" className="text-sm text-rose-300">
          {change.error.message}
        </p>
      )}
      <HudButton
        type="submit"
        variant="solid"
        className="w-full justify-center"
        disabled={!password || password !== repeat || change.isPending}
      >
        {change.isPending ? 'Guardando…' : 'Guardar y seguir'}
      </HudButton>
    </form>
  );
}

function CodeStep({
  pending,
  error,
  onSubmit,
}: {
  pending: boolean;
  error: Error | null;
  onSubmit: (code: string) => void;
}) {
  const [code, setCode] = useState('');
  return (
    <form
      className="space-y-3"
      onSubmit={(event) => {
        event.preventDefault();
        if (looksLikeCode(code)) onSubmit(code.replace(/\s/g, ''));
      }}
    >
      <CodeField value={code} onChange={setCode} />
      {error && (
        <p role="alert" className="text-sm text-rose-300">
          {error.message}
        </p>
      )}
      <HudButton
        type="submit"
        variant="solid"
        className="w-full justify-center"
        disabled={!looksLikeCode(code) || pending}
      >
        {pending ? 'Revisando…' : 'Entrar'}
      </HudButton>
    </form>
  );
}

export function LoginScreen() {
  const [step, setStep] = useState<LoginStep | null>(null);
  const openSession = useOpenSession();
  // Con el código apagado (ADR-0047) la contraseña basta: se entra directo.
  const advance = (next: LoginStep) => {
    if (next.next === 'done' && next.me) openSession(next.me);
    else setStep(next);
  };
  const finish = useMutation({
    mutationFn: ({ code, enrolling }: { code: string; enrolling: boolean }): Promise<Me> => {
      if (!step) throw new Error('Vuelve a escribir tu usuario y contraseña.');
      return enrolling ? confirmEnrollment(step.ticket, code) : submitCode(step.ticket, code);
    },
    onSuccess: openSession,
    onError: (error) => {
      // Si el ingreso venció o se agotaron los intentos, se vuelve a empezar.
      if (error.message.includes('Vuelve a escribir')) setStep(null);
    },
  });
  const current = TITLES[step?.next ?? 'credentials'];

  return (
    <div className="relative z-10 flex h-full items-center justify-center px-4">
      <HudPanel scan className="w-full max-w-md space-y-5 px-6 py-7">
        <div>
          <p className="mando-kicker">Oráculo · Monitor de Noticias</p>
          <h1 className="mt-2 text-xl font-semibold text-slate-50">{current.title}</h1>
          <p className="mt-2 text-sm text-slate-400">{current.help}</p>
        </div>
        {step === null && <CredentialsStep onDone={advance} />}
        {step?.next === 'change_password' && (
          <NewPasswordStep ticket={step.ticket} onDone={advance} />
        )}
        {step?.next === 'enroll' && (
          <EnrollStep
            ticket={step.ticket}
            pending={finish.isPending}
            error={finish.error}
            onConfirm={(code) => {
              finish.mutate({ code, enrolling: true });
            }}
          />
        )}
        {step?.next === 'code' && (
          <CodeStep
            pending={finish.isPending}
            error={finish.error}
            onSubmit={(code) => {
              finish.mutate({ code, enrolling: false });
            }}
          />
        )}
        {step !== null && (
          <button
            type="button"
            className="text-xs text-slate-400 underline-offset-2 hover:underline"
            onClick={() => {
              finish.reset();
              setStep(null);
            }}
          >
            ← Empezar de nuevo
          </button>
        )}
        <p className="text-xs text-slate-500">
          ¿Olvidaste tu contraseña o cambiaste de celular? Pídele al administrador que la
          restablezca desde «Accesos».
        </p>
      </HudPanel>
    </div>
  );
}
