/**
 * Textos y colores de la pantalla «Envíos» (ADR-0039): estados, proveedores y horas.
 *
 * No hace: no llama a la API.
 */
import type { AccountProvider, AccountStatus, DeliveryStatus } from '../../services/deliveries';
import type { ChipTone } from '../ui/HudChip';

export const PROVIDER_LABEL: Record<AccountProvider, string> = {
  outlook: 'Outlook / Hotmail',
  gmail: 'Gmail',
  whatsapp: 'WhatsApp',
};

export const ACCOUNT_STATUS: Record<AccountStatus, { label: string; tone: ChipTone }> = {
  pending: { label: 'Falta autorizar', tone: 'amber' },
  active: { label: 'Lista', tone: 'green' },
  failed: { label: 'Con error', tone: 'rose' },
  disabled: { label: 'Apagada', tone: 'slate' },
};

export const DELIVERY_STATUS: Record<DeliveryStatus, { label: string; tone: ChipTone }> = {
  pending: { label: 'Por enviar', tone: 'amber' },
  sending: { label: 'Enviando', tone: 'cyan' },
  sent: { label: 'Enviado', tone: 'green' },
  failed: { label: 'Falló', tone: 'rose' },
  skipped: { label: 'No se intentó', tone: 'slate' },
};

const WHEN = new Intl.DateTimeFormat('es-MX', {
  timeZone: 'America/Mexico_City',
  day: '2-digit',
  month: 'short',
  hour: '2-digit',
  minute: '2-digit',
});

/** «07 nov, 19:56» en hora de la Ciudad de México. */
export function whenLabel(iso: string): string {
  return WHEN.format(new Date(iso));
}

/**
 * Las horas de una regla, como se leen.
 *
 * @example hoursLabel([], [7, 15, 23]) // 'Todas las corridas'
 * @example hoursLabel([7, 15], [7, 15, 23]) // '07:00 y 15:00'
 */
export function hoursLabel(hours: readonly number[], all: readonly number[]): string {
  if (hours.length === 0 || all.every((h) => hours.includes(h))) return 'Todas las corridas';
  const names = hours.map((h) => `${String(h).padStart(2, '0')}:00`);
  return names.length === 1
    ? (names[0] ?? '')
    : `${names.slice(0, -1).join(', ')} y ${names.at(-1) ?? ''}`;
}
