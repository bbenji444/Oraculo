/**
 * Pantalla «Envíos» (F12.11, ADR-0039, ADR-0045).
 *
 * Cada persona da de alta sus correos (hasta dos) y elige a qué horas del
 * horario le llega el reporte de la FGR. El correo que envía y el horario los
 * decide el superusuario: él ve, además, las cuentas de envío, el horario y
 * los correos e historial de todos.
 *
 * Hoy se manda por correo (vía Composio); WhatsApp aparece como «Próximamente».
 * Está pensada para volverse el módulo de envíos de todo Oráculo: cada envío
 * lleva su «fuente», y mañana habrá más fuentes que el monitor.
 */
import { useMe } from '../../hooks/useAuth';
import { useDeliveryOverview } from '../../hooks/useDeliveries';
import { useSchedule } from '../../hooks/useSchedule';
import { HudChip } from '../ui/HudChip';
import { SectionHeading } from '../ui/SectionHeading';
import { AccountsPanel } from './AccountsPanel';
import { HistoryPanel } from './HistoryPanel';
import { RecipientsPanel } from './RecipientsPanel';
import { SchedulePanel } from './SchedulePanel';

/** Lo que ve un usuario normal: sus correos, sus horas y lo que se le ha mandado. */
function MyDeliveries({
  senderAddress,
  maxRecipients,
}: {
  senderAddress: string | null;
  maxRecipients: number | null;
}) {
  const times = useSchedule().data?.times ?? [];

  return (
    <div className="mx-auto max-w-4xl space-y-6 px-4 py-6 sm:px-6">
      <SectionHeading
        kicker="Automatizaciones"
        title="Mis envíos"
        description="Agrega tu correo y te llegará el reporte de la Fiscalía General de la República después de cada corrida automática."
      />
      <p className="rounded-lg border border-sky-400/20 bg-sky-400/5 px-4 py-3 text-sm text-slate-300">
        {times.length > 0 ? (
          <>
            Las corridas son a las <b className="text-slate-100">{times.join(', ')}</b> (hora de la
            Ciudad de México).
          </>
        ) : (
          'Las corridas siguen el horario que define el administrador.'
        )}{' '}
        {senderAddress ? (
          <>
            Te llega desde <b className="text-slate-100">{senderAddress}</b>.
          </>
        ) : (
          'El correo desde el que se manda lo define el administrador.'
        )}
      </p>
      <RecipientsPanel isSuperuser={false} maxRecipients={maxRecipients} />
      <HistoryPanel isSuperuser={false} senderAddress={senderAddress} />
    </div>
  );
}

export function DeliveriesPage() {
  const overview = useDeliveryOverview();
  const isSuperuser = useMe().data?.role === 'superuser';
  const data = overview.data;

  if (!isSuperuser) {
    return (
      <>
        {overview.error && (
          <p role="alert" className="mx-auto max-w-4xl px-6 pt-6 text-sm text-rose-300">
            {overview.error.message}
          </p>
        )}
        <MyDeliveries
          senderAddress={data?.sender_address ?? null}
          maxRecipients={data?.max_recipients ?? null}
        />
      </>
    );
  }

  return (
    <div className="mx-auto max-w-7xl space-y-6 px-4 py-6 sm:px-6">
      <SectionHeading
        kicker="Automatizaciones"
        title="Envíos"
        description="Un solo horario para todos: a cada hora se hace un reporte nuevo y se manda a cada persona a las horas que eligió. Cada envío queda registrado."
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
      <div className="grid items-start gap-6 lg:grid-cols-2">
        <AccountsPanel emailConfigured={data?.email_configured ?? false} />
        <RecipientsPanel isSuperuser />
      </div>
      <SchedulePanel />
      <HistoryPanel isSuperuser senderAddress={data?.sender_address ?? null} />
    </div>
  );
}
