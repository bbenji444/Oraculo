/**
 * Cada registro de la bitácora en una frase en español (pantalla «Accesos»).
 *
 * La bitácora guarda acciones técnicas (`access_key.revealed`) y sus datos;
 * aquí se vuelven frases para un analista: «Benji vio la llave de API de
 * Pepe». Los nombres salen de la lista de personas de «Accesos».
 *
 * No hace: no pide datos al servidor ni decide qué se ve (solo superusuarios).
 */
import type { AuditEvent, AuditGroup } from '../../services/access';
import type { ChipTone } from '../ui/HudChip';

/** Una persona, para poner su nombre en lugar de su usuario. */
export interface AuditPerson {
  id: number;
  username: string;
  display_name: string;
}

export interface AuditLine {
  /** La frase: «Benji vio la llave de API de Pepe». */
  text: string;
  /** Un dato corto extra (llave enmascarada, motivo, notas), o null. */
  extra: string | null;
  /** Grupo del registro, para su etiqueta. */
  group: Exclude<AuditGroup, 'all'> | 'other';
  /** Para resaltarlo: entradas fallidas y llaves vistas. */
  alert: boolean;
}

/** Los grupos del filtro, con su nombre en pantalla. */
export const AUDIT_GROUPS: readonly { value: AuditGroup; label: string }[] = [
  { value: 'all', label: 'Todo' },
  { value: 'access', label: 'Entradas y llaves' },
  { value: 'searches', label: 'Búsquedas' },
  { value: 'reports', label: 'Reportes' },
  { value: 'cases', label: 'Casos' },
  { value: 'concepts', label: 'Conceptos' },
];

export const GROUP_LABEL: Record<AuditLine['group'], string> = {
  access: 'Acceso',
  searches: 'Búsqueda',
  reports: 'Reporte',
  cases: 'Caso',
  concepts: 'Concepto',
  other: 'Otro',
};

export const GROUP_TONE: Record<AuditLine['group'], ChipTone> = {
  access: 'violet',
  searches: 'cyan',
  reports: 'green',
  cases: 'amber',
  concepts: 'slate',
  other: 'slate',
};

// Lo de antes del punto en la acción, por grupo (igual que el servidor,
// app/domain/audit_trail.py).
const GROUP_OF_PREFIX: Record<string, Exclude<AuditGroup, 'all'>> = {
  auth: 'access',
  user: 'access',
  access_key: 'access',
  search: 'searches',
  provider: 'searches',
  schedule: 'searches',
  report: 'reports',
  case: 'cases',
  entity: 'cases',
  entities: 'cases',
  relationship: 'cases',
  concept: 'concepts',
  category: 'concepts',
};

// Quienes no son personas: comandos, la carga inicial, el monitor.
const NOT_PEOPLE: Record<string, string> = {
  consola: 'La consola del servidor',
  semilla: 'La carga inicial',
  anonimo: 'Alguien sin cuenta',
  'monitor-automatico': 'El monitor automático',
  desarrollo: 'Modo desarrollo',
};

const VERBS: Record<string, string> = {
  created: 'creó',
  updated: 'editó',
  deleted: 'borró',
  closed: 'cerró',
  reopened: 'reabrió',
  archived: 'archivó',
  restored: 'restauró',
  viewed: 'abrió',
  confirmed: 'confirmó',
  discarded: 'descartó',
  merged: 'fusionó',
  unmerged: 'separó',
  split: 'dividió',
  merge_dismissed: 'descartó la fusión de',
};

// [con nombre, sin nombre]: «el caso «X»» o «un caso».
const NOUNS: Record<string, [string, string]> = {
  case: ['el caso', 'un caso'],
  concept: ['el concepto', 'un concepto'],
  category: ['la categoría', 'una categoría'],
  entity: ['', 'una entidad'],
  relationship: ['un vínculo', 'un vínculo'],
};

function text(value: unknown): string | null {
  return typeof value === 'string' && value.trim() !== '' ? value : null;
}

function record(value: unknown): Record<string, unknown> {
  return typeof value === 'object' && value !== null ? (value as Record<string, unknown>) : {};
}

function quoted(value: string | null): string {
  return value ? `«${value}»` : '';
}

/** Arma la frase de un registro. */
export function describeAudit(event: AuditEvent, people: readonly AuditPerson[]): AuditLine {
  const byName = new Map(people.map((p) => [p.username, p.display_name]));
  const byId = new Map(people.map((p) => [String(p.id), p.display_name]));
  const who = event.actor_name ?? NOT_PEOPLE[event.actor] ?? event.actor;
  const person = (username: unknown) => {
    const name = text(username);
    return name ? (byName.get(name) ?? name) : null;
  };
  const target = person(event.details.username) ?? byId.get(event.entity_id) ?? 'una persona';
  const [prefix = '', verb = ''] = event.action.split('.');
  const group = GROUP_OF_PREFIX[prefix] ?? 'other';
  const d = event.details;
  const line = (sentence: string, extra: string | null = null, alert = false): AuditLine => ({
    text: sentence,
    extra,
    group,
    alert,
  });

  switch (event.action) {
    case 'auth.login': {
      const method = text(d.metodo);
      return line(`${who} entró`, method ? `con ${method.replace('+', ' y ')}` : null);
    }
    case 'auth.login_failed':
      return line(
        event.actor === 'anonimo' ? 'Entrada fallida' : `Entrada fallida de ${who}`,
        text(d.motivo) ?? text(d.llave),
        true,
      );
    case 'auth.totp_setting':
      return line(
        d.pedir_codigo === true
          ? `${who} prendió el código al entrar`
          : `${who} apagó el código al entrar`,
      );
    case 'user.created':
      return line(`${who} dio de alta a ${target}`);
    case 'user.updated':
      return line(`${who} editó a ${target}`);
    case 'user.deleted':
      return line(`${who} borró a ${text(record(d.before).display_name) ?? target}`);
    case 'user.password_reset':
      return line(`${who} restableció la contraseña de ${target}`);
    case 'user.password_changed':
      return line(`${who} cambió su contraseña`);
    case 'user.totp_enrolled':
      return line(`${who} conectó Microsoft Authenticator`);
    case 'user.totp_reset':
      return line(`${who} reinició el autenticador de ${target}`);
    case 'access_key.created': {
      const owner = person(d.para) ?? 'una persona';
      return line(
        text(d.etiqueta) === 'Llave de API'
          ? `${who} generó la llave de API de ${owner}`
          : `${who} creó una llave de sistema para ${owner}`,
        text(d.llave),
      );
    }
    case 'access_key.revealed':
      return line(
        `${who} vio la llave de API de ${person(d.de) ?? 'una persona'}`,
        text(d.llave),
        true,
      );
    case 'access_key.revoked':
      return line(`${who} revocó una llave`);
    case 'search.finished': {
      const notes = typeof d.notas === 'number' ? `${String(d.notas)} notas` : null;
      const days =
        text(d.desde) && text(d.hasta) ? `${String(d.desde)} a ${String(d.hasta)}` : null;
      return line(`${who} terminó una búsqueda`, [notes, days].filter(Boolean).join(' · ') || null);
    }
    case 'search.reprocessed':
      return line(`${who} volvió a pasar notas por la IA`);
    case 'search.deleted':
      return line(`${who} quitó una búsqueda del historial`);
    case 'search.restored':
      return line(`${who} devolvió una búsqueda al historial`);
    case 'provider.query_executed':
      return line(
        `${who} consultó ${text(d.proveedor) ?? 'una fuente'}`,
        typeof d.resultados === 'number' ? `${String(d.resultados)} resultados` : null,
      );
    case 'schedule.updated':
      return line(`${who} cambió el horario de las corridas`);
    case 'report.generated': {
      const format = text(d.formato);
      return line(`${who} generó un reporte${format ? ` ${format.toUpperCase()}` : ''}`);
    }
    case 'case.article_added':
      return line(`${who} agregó una nota a un caso`);
    case 'case.article_removed':
      return line(`${who} quitó una nota de un caso`);
    case 'case.note_added':
      return line(`${who} escribió un comentario en un caso`);
    case 'case.member_added':
      return line(`${who} agregó a alguien a un caso`);
    case 'case.member_removed':
      return line(`${who} quitó a alguien de un caso`);
    case 'case.entity_added':
      return line(`${who} agregó una entidad a un caso`);
    case 'case.entities_extracted':
    case 'entities.extract':
      return line(`${who} sacó entidades de una nota con IA`);
    default:
      break;
  }

  const action = VERBS[verb];
  const noun = NOUNS[prefix];
  if (!action || !noun) return line(`${who}: ${event.action}`);
  if (prefix === 'relationship') {
    const a = text(record(d.entity_a).label);
    const b = text(record(d.entity_b).label);
    return line(`${who} ${action} un vínculo${a && b ? ` entre «${a}» y «${b}»` : ''}`);
  }
  const name =
    text(d.label) ?? text(record(d.after).name) ?? text(record(d.before).name) ?? text(d.name);
  const subject = name ? `${noun[0]} ${quoted(name)}`.trim() : noun[1];
  return line(`${who} ${action} ${subject}`);
}
