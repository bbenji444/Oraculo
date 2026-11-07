/**
 * Servicio de envíos (`/api/v1/deliveries`; docs/api.md, ADR-0039).
 *
 * Qué se manda, a quién, por qué canal y a qué hora: cuentas de envío
 * (Outlook o Gmail vía Composio; WhatsApp más adelante), destinatarios,
 * reglas e historial de cada envío con sus intentos.
 *
 * Los componentes nunca llaman a fetch directamente (CLAUDE.md §6.2).
 */
import { apiUrl } from '../config/api';
import { ApiError, badFormat, requestJson } from './http';

export type AccountProvider = 'outlook' | 'gmail' | 'whatsapp';
export type DeliveryChannel = 'email' | 'whatsapp';
export type AccountStatus = 'pending' | 'active' | 'failed' | 'disabled';
export type DeliveryStatus = 'pending' | 'sending' | 'sent' | 'failed' | 'skipped';

export interface DeliveryOverview {
  /** Si las corridas automáticas mandan (DELIVERIES_ENABLED). */
  enabled: boolean;
  /** Si hay llave de Composio para el correo. */
  email_configured: boolean;
  whatsapp_available: boolean;
  sources: { id: string; label: string }[];
  /** Horas de las corridas automáticas (CDMX). */
  run_hours: number[];
}

export interface DeliveryAccount {
  id: number;
  provider: AccountProvider;
  channel: DeliveryChannel;
  label: string;
  address: string | null;
  status: AccountStatus;
}

export interface RecipientInput {
  name: string;
  email: string | null;
  phone: string | null;
  is_active: boolean;
}

export interface Recipient extends RecipientInput {
  id: number;
}

export interface RuleInput {
  source: string;
  recipient_id: number;
  channel: DeliveryChannel;
  account_id: number | null;
  /** Horas de la CDMX; vacío = todas las corridas. */
  hours: number[];
  is_active: boolean;
}

export interface Rule extends RuleInput {
  id: number;
}

export interface DeliveryAttempt {
  attempt: number;
  ok: boolean;
  provider_status: string | null;
  error: string | null;
  started_at: string;
  finished_at: string;
}

export interface Delivery {
  id: string;
  source: string;
  source_label: string;
  source_ref: string;
  rule_id: number | null;
  channel: DeliveryChannel;
  account_id: number | null;
  recipient_id: number | null;
  recipient_name: string | null;
  /** Enmascarado: be•••@hotmail.com. */
  destination: string;
  subject: string;
  attachment_name: string | null;
  status: DeliveryStatus;
  attempts: number;
  last_error: string | null;
  provider_ref: string | null;
  is_test: boolean;
  created_at: string;
  sent_at: string | null;
  next_attempt_at: string | null;
  attempt_log: DeliveryAttempt[];
}

export interface DeliveryPage {
  items: Delivery[];
  next_cursor: string | null;
}

/** Problemas de validación por campo, como los entrega la API. */
export type DeliveryFieldErrors = Record<string, string[]>;

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null;
}

function asList<T>(body: unknown, guard: (item: unknown) => boolean): T[] {
  if (!Array.isArray(body) || !body.every(guard)) throw badFormat();
  return body as T[];
}

const hasId = (value: unknown) => isRecord(value) && typeof value.id === 'number';

const url = (path = '') => apiUrl(`deliveries${path}`);

/** Estado general de los envíos. */
export async function getDeliveryOverview(signal?: AbortSignal): Promise<DeliveryOverview> {
  const body = await requestJson(url('/overview'), { signal });
  if (!isRecord(body) || typeof body.enabled !== 'boolean' || !Array.isArray(body.sources)) {
    throw badFormat();
  }
  return body as unknown as DeliveryOverview;
}

/** Cuentas desde las que se manda. */
export async function listAccounts(signal?: AbortSignal): Promise<DeliveryAccount[]> {
  return asList<DeliveryAccount>(await requestJson(url('/accounts'), { signal }), hasId);
}

/**
 * Conecta una cuenta de correo: devuelve la cuenta pendiente y el link de autorización.
 *
 * @throws {ApiError} `delivery_channel_unavailable` sin llave de Composio o con WhatsApp.
 */
export async function connectAccount(
  provider: AccountProvider,
  label: string,
): Promise<{ account: DeliveryAccount; connect_url: string }> {
  const body = await requestJson(url('/accounts'), { method: 'POST', body: { provider, label } });
  if (!isRecord(body) || typeof body.connect_url !== 'string' || !hasId(body.account)) {
    throw badFormat();
  }
  return body as unknown as { account: DeliveryAccount; connect_url: string };
}

/** Pregunta al proveedor si la cuenta ya quedó autorizada. */
export async function refreshAccount(id: number): Promise<DeliveryAccount> {
  const body = await requestJson(url(`/accounts/${String(id)}/refresh`), { method: 'POST' });
  if (!hasId(body)) throw badFormat();
  return body as DeliveryAccount;
}

/** Destinatarios. */
export async function listRecipients(signal?: AbortSignal): Promise<Recipient[]> {
  return asList<Recipient>(await requestJson(url('/recipients'), { signal }), hasId);
}

/** Guarda un destinatario nuevo o editado. */
export async function saveRecipient(input: RecipientInput, id?: number): Promise<Recipient> {
  const body = await requestJson(id ? url(`/recipients/${String(id)}`) : url('/recipients'), {
    method: id ? 'PUT' : 'POST',
    body: input,
  });
  if (!hasId(body)) throw badFormat();
  return body as Recipient;
}

/** Reglas de envío. */
export async function listRules(signal?: AbortSignal): Promise<Rule[]> {
  return asList<Rule>(await requestJson(url('/rules'), { signal }), hasId);
}

/** Guarda una regla nueva o editada. */
export async function saveRule(input: RuleInput, id?: number): Promise<Rule> {
  const body = await requestJson(id ? url(`/rules/${String(id)}`) : url('/rules'), {
    method: id ? 'PUT' : 'POST',
    body: input,
  });
  if (!hasId(body)) throw badFormat();
  return body as Rule;
}

const isDelivery = (value: unknown) =>
  isRecord(value) && typeof value.id === 'string' && typeof value.status === 'string';

/** Historial de envíos, del más nuevo al más viejo. */
export async function listDeliveries(signal?: AbortSignal): Promise<DeliveryPage> {
  const body = await requestJson(url('/history'), { signal });
  if (!isRecord(body) || !Array.isArray(body.items) || !body.items.every(isDelivery)) {
    throw badFormat();
  }
  return body as unknown as DeliveryPage;
}

/** Vuelve a intentar un envío fallido. */
export async function retryDelivery(id: string): Promise<Delivery> {
  const body = await requestJson(url(`/history/${id}/retry`), { method: 'POST' });
  if (!isDelivery(body)) throw badFormat();
  return body as Delivery;
}

/** «Mandar prueba»: la última corrida a un destinatario, ya. */
export async function sendTest(recipientId: number, accountId: number): Promise<Delivery> {
  const body = await requestJson(url('/test'), {
    method: 'POST',
    body: { recipient_id: recipientId, account_id: accountId },
  });
  if (!isDelivery(body)) throw badFormat();
  return body as Delivery;
}

/**
 * Traduce un error de validación a mensajes por campo.
 *
 * @param error El error de la mutación.
 * @returns Los mensajes por campo; vacío si no es de validación.
 */
export function deliveryFieldErrors(error: unknown): DeliveryFieldErrors {
  if (!(error instanceof ApiError) || error.code !== 'invalid_delivery') return {};
  const problems = error.details.problemas;
  const result: DeliveryFieldErrors = {};
  if (!Array.isArray(problems)) return result;
  for (const problem of problems as { campo?: unknown; mensaje?: unknown }[]) {
    if (typeof problem.campo !== 'string' || typeof problem.mensaje !== 'string') continue;
    (result[problem.campo] ??= []).push(problem.mensaje);
  }
  return result;
}
