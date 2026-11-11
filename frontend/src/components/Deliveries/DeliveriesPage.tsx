/**
 * Pantalla «Envíos» (F12.11, ADR-0039, ADR-0045, ADR-0046).
 *
 * Cada persona arma sus envíos programados: qué temas, de qué región, a qué
 * horas, qué días y a cuáles de sus correos (hasta dos), y con «Mandar
 * prueba» ve cómo le llega. El superusuario además conecta la cuenta desde la
 * que se manda y ve los envíos, correos y la bitácora de correos de todos
 * (Benji, 11/11/2026: al usuario esa bitácora le sobra).
 *
 * Hoy se manda por correo (vía Composio); WhatsApp aparece como «Próximamente».
 * Está pensada para volverse el módulo de envíos de todo Oráculo: cada envío
 * lleva su «fuente», y mañana habrá más fuentes que el monitor.
 */
import { useMe } from '../../hooks/useAuth';
import { useDeliveryOverview } from '../../hooks/useDeliveries';
import { HudChip } from '../ui/HudChip';
import { SectionHeading } from '../ui/SectionHeading';
import { AccountsPanel } from './AccountsPanel';
import { HistoryPanel } from './HistoryPanel';
import { RecipientsPanel } from './RecipientsPanel';
import { SchedulesPanel } from './SchedulesPanel';

export function DeliveriesPage() {
  const overview = useDeliveryOverview();
  const me = useMe().data;
  const isSuperuser = me?.role === 'superuser';
  const username = me?.username ?? '';
  const data = overview.data;

  if (!isSuperuser) {
    return (
      <div className="mx-auto max-w-5xl space-y-6 px-4 py-6 sm:px-6">
        <SectionHeading
          kicker="Automatizaciones"
          title="Mis envíos"
          description="Arma tus propios reportes: elige los temas, de dónde, a qué horas y qué días te llegan a tu correo."
        />
        {overview.error && (
          <p role="alert" className="text-sm text-rose-300">
            {overview.error.message}
          </p>
        )}
        <SchedulesPanel isSuperuser={false} username={username} />
        <RecipientsPanel isSuperuser={false} maxRecipients={data?.max_recipients ?? null} />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-7xl space-y-6 px-4 py-6 sm:px-6">
      <SectionHeading
        kicker="Automatizaciones"
        title="Envíos"
        description="Cada persona programa sus envíos: temas, región, horas y días. Los que piden lo mismo a la misma hora comparten una sola corrida. Cada envío queda registrado."
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
          Las corridas se siguen haciendo, pero todavía <b>no mandan correos</b>: prueba con «Mandar
          prueba». Para encenderlos, pon <code className="font-mono">DELIVERIES_ENABLED=true</code>{' '}
          en el .env y reinicia los servicios.
        </p>
      )}
      {overview.error && (
        <p role="alert" className="text-sm text-rose-300">
          {overview.error.message}
        </p>
      )}
      <SchedulesPanel isSuperuser username={username} />
      <div className="grid items-start gap-6 lg:grid-cols-2">
        <AccountsPanel emailConfigured={data?.email_configured ?? false} />
        <RecipientsPanel isSuperuser />
      </div>
      <HistoryPanel isSuperuser />
    </div>
  );
}
