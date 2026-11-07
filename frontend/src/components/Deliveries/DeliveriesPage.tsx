/**
 * Pantalla «Envíos» (F12.11, ADR-0039).
 *
 * Qué se manda, a quién, por qué canal y a qué hora. Hoy, el reporte de cada
 * corrida FGR por correo (vía Composio); WhatsApp aparece como «Próximamente».
 * Está pensada para volverse el módulo de envíos de todo Oráculo: cada envío
 * lleva su «fuente», y mañana habrá más fuentes que el monitor.
 *
 * Arriba, el estado: si las corridas automáticas ya mandan (DELIVERIES_ENABLED)
 * y si el correo está listo.
 */
import { useDeliveryOverview } from '../../hooks/useDeliveries';
import { HudChip } from '../ui/HudChip';
import { SectionHeading } from '../ui/SectionHeading';
import { AccountsPanel } from './AccountsPanel';
import { HistoryPanel } from './HistoryPanel';
import { RecipientsPanel } from './RecipientsPanel';
import { RulesPanel } from './RulesPanel';

export function DeliveriesPage() {
  const overview = useDeliveryOverview();
  const data = overview.data;

  return (
    <div className="mx-auto max-w-7xl space-y-6 px-4 py-6 sm:px-6">
      <SectionHeading
        kicker="Automatizaciones"
        title="Envíos"
        description="Qué se manda, a quién, por qué canal y a qué hora. Cada envío queda registrado."
        actions={
          data && (
            <div className="flex flex-wrap gap-2">
              <HudChip tone={data.enabled ? 'green' : 'amber'} dot live={data.enabled}>
                {data.enabled ? 'Envíos automáticos prendidos' : 'Envíos automáticos apagados'}
              </HudChip>
              <HudChip tone={data.email_configured ? 'green' : 'rose'} dot>
                {data.email_configured ? 'Correo listo' : 'Correo sin configurar'}
              </HudChip>
              <HudChip tone="slate">WhatsApp · Próximamente</HudChip>
            </div>
          )
        }
      />
      {data && !data.enabled && (
        <p className="rounded-lg border border-amber-400/30 bg-amber-400/10 px-4 py-3 text-sm text-amber-100">
          Las corridas automáticas todavía <b>no mandan nada</b>: arma tus reglas y prueba con
          «Mandar prueba». Para encenderlos, pon{' '}
          <code className="font-mono">DELIVERIES_ENABLED=true</code> en el .env y reinicia los
          servicios.
        </p>
      )}
      {overview.error && (
        <p role="alert" className="text-sm text-rose-300">
          {overview.error.message}
        </p>
      )}
      <div className="grid gap-6 lg:grid-cols-2">
        <div className="space-y-6">
          <AccountsPanel emailConfigured={data?.email_configured ?? false} />
          <RecipientsPanel />
        </div>
        <RulesPanel />
      </div>
      <HistoryPanel />
    </div>
  );
}
