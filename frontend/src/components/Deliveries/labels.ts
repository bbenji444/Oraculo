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
