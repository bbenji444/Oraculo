/**
 * «Bitácora» de la pantalla «Accesos» (solo superusuarios).
 *
 * Benji, 11/11/2026: «¿a qué bitácora te refieres?». Es el registro de quién
 * hizo qué: quién entró (y los intentos fallidos), quién vio o generó cada
 * llave, quién buscó, generó reportes o cambió casos y conceptos. Cada fila
 * dice cuándo y desde qué IP. Lo más nuevo va arriba; «Ver más» trae lo
 * anterior.
 *
 * Se filtra por grupo («Entradas y llaves», «Búsquedas»…) y por persona.
 *
 * No hace: no borra nada (la bitácora es de solo agregar) ni muestra llaves
 * completas: el servidor solo guarda su parte pública.
 */
import { type CSSProperties, useId, useState } from 'react';

import { useAuditTrail } from '../../hooks/useAccess';
import type { AccessUser, AuditEvent, AuditGroup } from '../../services/access';
import { formatMexicoCity } from '../Explore/format';
import { HudButton } from '../ui/HudButton';
import { HudChip } from '../ui/HudChip';
import { HudPanel } from '../ui/HudPanel';
import { HudSelect } from '../ui/HudSelect';
import {
  AUDIT_GROUPS,
  type AuditPerson,
  describeAudit,
  GROUP_LABEL,
  GROUP_TONE,
} from './auditText';

// Las entradas escalonadas se cortan aquí: una página larga no debe tardar en aparecer.
const MAX_STAGGER = 12;
// «Todas las personas» en el filtro (ningún usuario se llama así: no puede estar vacío).
const EVERYONE = '';

function AuditRow({
  event,
  people,
  index,
}: {
  event: AuditEvent;
  people: readonly AuditPerson[];
  index: number;
}) {
  const line = describeAudit(event, people);
  return (
    <li
      className="hud-reveal flex flex-wrap items-start gap-x-4 gap-y-1 border-b border-sky-400/10 py-3 last:border-b-0"
      style={{ '--i': Math.min(index, MAX_STAGGER) } as CSSProperties}
    >
      <div className="w-24 shrink-0 pt-0.5">
        <HudChip tone={line.alert ? 'rose' : GROUP_TONE[line.group]}>
          {GROUP_LABEL[line.group]}
        </HudChip>
      </div>
      <div className="min-w-0 flex-1 basis-56">
        <p className="text-sm text-slate-100">{line.text}</p>
        <p className="mt-0.5 text-[11px] text-slate-500">
          {formatMexicoCity(event.created_at)}
          {event.ip ? ` · desde ${event.ip}` : ''}
          {line.extra && (
            <>
              {' · '}
              <span className="font-mono text-slate-400">{line.extra}</span>
            </>
          )}
        </p>
      </div>
    </li>
  );
}

export function AuditTrail({ people }: { people: readonly AccessUser[] }) {
  const id = useId();
  const [group, setGroup] = useState<AuditGroup>('all');
  const [actor, setActor] = useState(EVERYONE);
  const trail = useAuditTrail(group, actor === EVERYONE ? null : actor);
  const events = trail.data?.pages.flatMap((page) => page.items) ?? [];

  return (
    <section aria-label="Bitácora" className="mt-6">
      <HudPanel className="px-5 py-4">
        <p className="font-medium text-slate-50">Bitácora: quién hizo qué</p>
        <p className="mt-0.5 text-xs text-slate-400">
          Quién entró al monitor, quién vio o generó cada llave y quién buscó o cambió algo, con la
          hora y desde dónde. Nada se borra de aquí.
        </p>
        <div className="mt-4 grid gap-3 sm:grid-cols-2">
          <div>
            <label htmlFor={`${id}-que`} className="hud-label">
              Qué
            </label>
            <HudSelect
              id={`${id}-que`}
              size="sm"
              value={group}
              options={AUDIT_GROUPS}
              onChange={setGroup}
            />
          </div>
          <div>
            <label htmlFor={`${id}-quien`} className="hud-label">
              Quién
            </label>
            <HudSelect
              id={`${id}-quien`}
              size="sm"
              value={actor}
              options={[
                { value: EVERYONE, label: 'Todas las personas' },
                ...people.map((p) => ({ value: p.username, label: p.display_name })),
              ]}
              onChange={setActor}
            />
          </div>
        </div>
      </HudPanel>
      <HudPanel className="mt-3 px-5 py-2">
        {trail.isPending && <p className="py-3 text-sm text-slate-400">Cargando…</p>}
        {trail.error && <p className="py-3 text-sm text-rose-300">{trail.error.message}</p>}
        {trail.isSuccess && events.length === 0 && (
          <p className="py-3 text-sm text-slate-400">No hay registros con estos filtros.</p>
        )}
        <ul>
          {events.map((event, index) => (
            <AuditRow key={event.id} event={event} people={people} index={index} />
          ))}
        </ul>
        {trail.hasNextPage && (
          <div className="py-3 text-center">
            <HudButton
              size="sm"
              variant="ghost"
              disabled={trail.isFetchingNextPage}
              onClick={() => {
                void trail.fetchNextPage();
              }}
            >
              {trail.isFetchingNextPage ? 'Cargando…' : 'Ver más'}
            </HudButton>
          </div>
        )}
      </HudPanel>
    </section>
  );
}
