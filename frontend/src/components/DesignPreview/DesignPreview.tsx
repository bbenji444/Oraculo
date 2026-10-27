/**
 * Muestra del diseño «consola táctica» (27/10/2026), para que Benji lo apruebe
 * antes de aplicarlo a todas las pantallas.
 *
 * Se abre con `?diseno` en la URL (#/diseno). Cada bloque es una pantalla del
 * monitor en pequeño, armada con las piezas de src/components/ui y con datos
 * reales del proyecto (corrida FGR de las 23:00 del 26/10/2026, los casos y
 * titulares guardados). No llama a la API: los datos van escritos aquí.
 *
 * No hace: no reemplaza ninguna pantalla real.
 */
import { type CSSProperties, type ReactNode, useState } from 'react';

import { CountUp } from '../ui/CountUp';
import { Heartbeat } from '../ui/Heartbeat';
import { ArrowIcon, HudButton } from '../ui/HudButton';
import { HudChip, type ChipTone } from '../ui/HudChip';
import { HudPanel } from '../ui/HudPanel';
import { HudSegmented } from '../ui/HudSegmented';
import { HudSwitch } from '../ui/HudSwitch';
import { SectionHeading } from '../ui/SectionHeading';
import { Sparkline } from '../ui/Sparkline';

// Corrida FGR de las 23:00 del 26/10/2026 (búsqueda a07ada8a).
const KPIS = [
  { label: 'Notas relevantes', value: 175, trend: [12, 18, 9, 22, 31, 27, 40, 16] },
  { label: 'Hechos nuevos', value: 33, trend: [4, 7, 3, 9, 6, 11, 8, 5] },
  { label: 'Estados con notas', value: 14, trend: [8, 9, 9, 11, 12, 12, 13, 14] },
  { label: 'Notas nuevas', value: 98, trend: [20, 35, 28, 51, 44, 67, 80, 98] },
];

// Los casos guardados al 27/10/2026, tal como salen en la pestaña Casos.
const CASES: {
  name: string;
  notes: number;
  updated: string;
  status: [string, ChipTone];
  level: [string, ChipTone];
}[] = [
  {
    name: 'Balacera Iztapalapa - Ermita',
    notes: 4,
    updated: '24 oct',
    status: ['Abierto', 'green'],
    level: ['Normal', 'slate'],
  },
  {
    name: 'fgr',
    notes: 4,
    updated: '24 oct',
    status: ['Abierto', 'green'],
    level: ['Normal', 'slate'],
  },
  {
    name: 'prueba',
    notes: 1,
    updated: '23 oct',
    status: ['Cerrado', 'slate'],
    level: ['Normal', 'slate'],
  },
  {
    name: 'Homicidio estilista Polanco',
    notes: 8,
    updated: '23 oct',
    status: ['Abierto', 'green'],
    level: ['Reservado', 'amber'],
  },
];

const SERVICES = [
  { name: 'API', detail: 'Respuesta 0.1 ms', ok: true },
  { name: 'Base de datos', detail: 'PostgreSQL 16 · PostGIS 3.6', ok: true },
  { name: 'Cola y caché', detail: 'Redis 8.0', ok: true },
  { name: 'Worker', detail: '1 proceso · corridas 07 · 15 · 23 h', ok: true },
];

const RANGES = [
  { value: 'hoy', label: 'Hoy' },
  { value: '7', label: '7 días' },
  { value: '30', label: '30 días' },
  { value: 'otro', label: 'Otro' },
] as const;

type Range = (typeof RANGES)[number]['value'];

/** Lupa del buscador. */
function SearchIcon() {
  return (
    <svg
      viewBox="0 0 20 20"
      width="16"
      height="16"
      fill="none"
      stroke="currentColor"
      aria-hidden="true"
    >
      <circle cx="9" cy="9" r="5.5" strokeWidth="1.6" />
      <path d="m13.5 13.5 3.5 3.5" strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  );
}

function Block({ index, title, children }: { index: number; title: string; children: ReactNode }) {
  return (
    <section className="hud-reveal" style={{ '--i': index } as CSSProperties}>
      <p className="mb-3 font-display text-[10px] tracking-[0.3em] text-slate-500">
        {String(index).padStart(2, '0')} · {title}
      </p>
      {children}
    </section>
  );
}

function Kpis() {
  return (
    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
      {KPIS.map((kpi, i) => (
        <HudPanel
          key={kpi.label}
          interactive
          scan
          className="hud-reveal p-5"
          style={{ '--i': i } as CSSProperties}
        >
          <p className="hud-kpi-label">{kpi.label}</p>
          <div className="mt-4 flex items-end justify-between gap-3">
            <CountUp value={kpi.value} className="hud-kpi-value" />
            <Sparkline values={kpi.trend} />
          </div>
        </HudPanel>
      ))}
    </div>
  );
}

function Buttons() {
  return (
    <HudPanel className="flex flex-wrap items-center gap-3 p-5">
      <HudButton variant="solid" icon={<ArrowIcon />}>
        Buscar noticias
      </HudButton>
      <HudButton icon={<ArrowIcon />}>Abrir en el globo</HudButton>
      <HudButton>Descargar reporte (PDF)</HudButton>
      <HudButton variant="ghost">Ocultar</HudButton>
      <HudButton variant="danger">Eliminar caso</HudButton>
      <HudButton size="sm">+ Nuevo caso</HudButton>
      <span className="mx-1 h-8 w-px bg-sky-400/20" aria-hidden="true" />
      <button type="button" className="hud-icon-btn" aria-label="Acercar">
        +
      </button>
      <button type="button" className="hud-icon-btn" aria-label="Alejar">
        −
      </button>
      <span className="flex flex-wrap gap-2">
        <HudChip tone="green" live>
          En vivo
        </HudChip>
        <HudChip tone="amber" dot>
          Reservado
        </HudChip>
        <HudChip tone="violet">Seguridad nacional</HudChip>
        <HudChip>FGR federal</HudChip>
      </span>
    </HudPanel>
  );
}

function SearchMock() {
  const [range, setRange] = useState<Range>('7');
  const [rss, setRss] = useState(true);
  const [index, setIndex] = useState(true);
  const [searchApi, setSearchApi] = useState(false);
  return (
    <HudPanel className="space-y-5 p-5">
      <div className="flex items-center justify-between">
        <p className="hud-kicker">Buscar noticias</p>
        <HudButton variant="ghost" size="sm">
          Ocultar
        </HudButton>
      </div>
      <label className="hud-field">
        <span className="text-sky-300/70">
          <SearchIcon />
        </span>
        <input placeholder="Busca: Iztapalapa, CDMX, Peñón Blanco…" aria-label="Lugar" />
      </label>
      <HudSegmented label="Periodo" options={RANGES} value={range} onChange={setRange} />
      <div className="space-y-2">
        {[
          ['Google News RSS', 'Gratis', rss, setRss],
          ['Índice local (GDELT + medios)', 'Gratis', index, setIndex],
          ['SearchApi (Google News)', 'Gasta créditos', searchApi, setSearchApi],
        ].map(([name, cost, on, set]) => (
          <div key={name as string} className="hud-row cursor-default">
            <span>
              <span className="block text-sm text-slate-100">{name as string}</span>
              <span
                className={`text-xs ${cost === 'Gratis' ? 'text-emerald-300/80' : 'text-amber-300/90'}`}
              >
                {cost as string}
              </span>
            </span>
            <span className="ml-auto">
              <HudSwitch
                label={name as string}
                checked={on as boolean}
                onChange={set as (v: boolean) => void}
              />
            </span>
          </div>
        ))}
      </div>
      <HudButton variant="solid" className="w-full" icon={<ArrowIcon />}>
        Buscar · 0 créditos
      </HudButton>
    </HudPanel>
  );
}

function CasesMock() {
  const [active, setActive] = useState(0);
  return (
    <HudPanel className="p-2">
      {CASES.map((item, i) => (
        <div
          key={item.name}
          role="button"
          tabIndex={0}
          aria-current={i === active}
          className="hud-row hud-reveal"
          style={{ '--i': i } as CSSProperties}
          onClick={() => {
            setActive(i);
          }}
          onKeyDown={(event) => {
            if (event.key === 'Enter') setActive(i);
          }}
        >
          <span className="min-w-0">
            <span className="block truncate text-[15px] font-medium text-slate-50">
              {item.name}
            </span>
            <span className="mt-1 block text-xs text-slate-400">
              {item.notes} {item.notes === 1 ? 'nota' : 'notas'} · actualizado {item.updated}
            </span>
          </span>
          <span className="ml-auto flex shrink-0 gap-2">
            <HudChip tone={item.status[1]} dot>
              {item.status[0]}
            </HudChip>
            <HudChip tone={item.level[1]}>{item.level[0]}</HudChip>
          </span>
          <span className="hud-row-arrow">
            <ArrowIcon />
          </span>
        </div>
      ))}
    </HudPanel>
  );
}

function NewsCardMock() {
  return (
    <HudPanel interactive className="p-5">
      <div className="flex flex-wrap gap-2">
        <HudChip tone="violet">Seguridad nacional</HudChip>
        <HudChip dot>FGR federal</HudChip>
        <HudChip tone="green">Nuevo</HudChip>
      </div>
      <h3 className="mt-4 text-lg font-medium leading-snug text-slate-50">
        Vinculan a proceso a César Jáuregui por traición a la patria; seguirá en el Altiplano
      </h3>
      <p className="mt-1 text-xs text-slate-400">
        infobae.com · 25 oct, 02:21 · Almoloya de Juárez
      </p>
      <p className="mt-3 text-sm leading-relaxed text-slate-300">
        Un juez federal vinculó a proceso al exfiscal por traición a la patria y ordenó que
        permanezca en prisión preventiva. La FGR presentó más de 150 datos de prueba.
      </p>
      <div className="mt-4">
        <div className="flex justify-between text-[10px] tracking-[0.2em] text-slate-400">
          <span className="font-display">CONFIANZA</span>
          <span className="font-display text-sky-200">92 %</span>
        </div>
        <div className="hud-meter mt-2">
          <span style={{ '--value': '92%' } as CSSProperties} />
        </div>
      </div>
      <div className="mt-5 flex gap-2">
        <HudButton size="sm" icon={<ArrowIcon />}>
          Ver nota original
        </HudButton>
        <HudButton size="sm" variant="ghost">
          + Agregar a caso
        </HudButton>
      </div>
    </HudPanel>
  );
}

function RunMock() {
  return (
    <HudPanel interactive scan className="flex flex-wrap items-center gap-4 p-5">
      <span className="hud-radar" aria-hidden="true" />
      <div className="min-w-0 flex-1 basis-64">
        <p className="font-display text-[10px] tracking-[0.28em] text-sky-300">
          MONITOR AUTOMÁTICO · CORRIDA DE LAS 23:00
        </p>
        <p className="mt-1 truncate text-base font-medium text-slate-50">
          Fiscalía General de la República · México
        </p>
        <p className="mt-1 text-xs text-slate-400">
          26 oct · <CountUp value={292} /> notas · 0 créditos · 0.0276 USD
        </p>
      </div>
      <HudChip tone="green" dot>
        Terminada
      </HudChip>
      <HudButton icon={<ArrowIcon />}>Abrir en el globo</HudButton>
    </HudPanel>
  );
}

function StatusMock() {
  return (
    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
      {SERVICES.map((service, i) => (
        <HudPanel
          key={service.name}
          className="hud-reveal p-4"
          style={{ '--i': i } as CSSProperties}
        >
          <div className="flex items-center justify-between">
            <span className="text-sm font-medium text-slate-50">{service.name}</span>
            <HudChip tone="green" live>
              OK
            </HudChip>
          </div>
          <Heartbeat ok delaySeconds={i * 0.35} className="mt-3" />
          <p className="mt-2 text-xs text-slate-400">{service.detail}</p>
        </HudPanel>
      ))}
    </div>
  );
}

export function DesignPreview() {
  return (
    <div className="mx-auto max-w-6xl space-y-10 px-4 pb-16 pt-8 sm:px-6">
      <SectionHeading
        kicker="Propuesta de diseño · consola táctica"
        title="Así se vería el monitor"
        description="Pasa el mouse por cada pieza: los paneles se iluminan donde está el cursor, los botones destellan y se hunden al hacer clic, las cifras corren, los títulos se descifran. Datos reales de la corrida de las 23:00 del 26/10."
        actions={
          <>
            <HudButton variant="ghost">Cancelar</HudButton>
            <HudButton variant="solid" icon={<ArrowIcon />}>
              Aprobar diseño
            </HudButton>
          </>
        }
      />
      <Block index={1} title="Cifras del panorama">
        <Kpis />
      </Block>
      <Block index={2} title="Botones e insignias">
        <Buttons />
      </Block>
      <div className="grid gap-10 lg:grid-cols-2">
        <Block index={3} title="Explorar · panel de búsqueda">
          <SearchMock />
        </Block>
        <Block index={4} title="Explorar · ficha de una nota">
          <NewsCardMock />
        </Block>
      </div>
      <Block index={5} title="Casos · lista">
        <CasesMock />
      </Block>
      <Block index={6} title="Historial · corrida automática">
        <RunMock />
      </Block>
      <Block index={7} title="Estado del sistema">
        <StatusMock />
      </Block>
    </div>
  );
}
