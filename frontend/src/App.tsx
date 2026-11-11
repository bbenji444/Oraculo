/**
 * Componente raíz: encabezado con pestañas y la pantalla activa.
 *
 * Pestañas: "Explorar" (globo, búsqueda y resultados, F6), "Casos" (casos de
 * investigación con sus noticias, F9.3), "Conceptos" (administración y "Probar
 * concepto", F2), "Historial" (búsquedas anteriores, F6) y "Estado del sistema"
 * (F0). La pestaña vive en la URL (#/explorar, #/casos, #/conceptos, #/historial,
 * #/estado) para que se pueda compartir o recargar
 * sin perderla; #/geodatos sigue llevando a Explorar. No hace llamadas HTTP.
 *
 * Acceso (ADR-0042 y ADR-0043): sin sesión se ve «Entrar» (usuario,
 * contraseña y código de Microsoft Authenticator, igual que Oráculo). Con
 * sesión, solo las pestañas del rol de la persona: «Estado del sistema» y
 * «Accesos» (#/accesos) son de superusuarios. La sesión (nombre, «Mi
 * contraseña» y «Salir») va en una cápsula del encabezado (`UserCapsule`).
 *
 * Con `?laboratorio` en la URL aparece además "Laboratorio" (#/laboratorio):
 * el laboratorio del muro de la Fase 9.1 (ADR-0102). Se carga aparte, solo al
 * abrirlo, para no pesar en Explorar.
 */
import { lazy, type ReactNode, Suspense, useEffect, useState } from 'react';

import { AccessPage } from './components/Access/AccessPage';
import { LoginScreen } from './components/Auth/LoginScreen';
import { UserCapsule } from './components/Auth/UserCapsule';
import { CasesPage } from './components/Cases/CasesPage';
import { ConceptsPage } from './components/Concepts/ConceptsPage';
import { ExplorePage } from './components/Explore/ExplorePage';
import { GraphicsBoundary } from './components/Explore/GraphicsBoundary';
import { SpaceBackground } from './components/Space/SpaceBackground';
import { DesignPreview } from './components/DesignPreview/DesignPreview';
import { HistoryPage } from './components/History/HistoryPage';
import { DeliveriesPage } from './components/Deliveries/DeliveriesPage';
import { SystemStatusPanel } from './components/SystemStatus/SystemStatusPanel';
import { HudTabs } from './components/ui/HudTabs';
import { useAppConfig } from './hooks/useAppConfig';
import { useMe } from './hooks/useAuth';
import type { Me, Section } from './services/auth';
import { safeOraculoUrl } from './services/appConfig';
import { installSpotlight } from './ui/spotlight';

type Tab = Section | 'laboratorio' | 'diseno';

const MuroLab = lazy(() => import('./lab/MuroLab'));
// El laboratorio es solo para desarrollo: se pide a propósito en la URL.
const LAB_ENABLED = new URLSearchParams(window.location.search).has('laboratorio');
// La muestra del diseño nuevo (27/10/2026): solo con ?diseno en la URL.
const DESIGN_ENABLED = new URLSearchParams(window.location.search).has('diseno');

const ALL_TABS: { id: Tab; label: string }[] = [
  { id: 'explorar', label: 'Explorar' },
  { id: 'casos', label: 'Casos' },
  { id: 'conceptos', label: 'Conceptos' },
  { id: 'historial', label: 'Historial' },
  { id: 'envios', label: 'Envíos' },
  { id: 'estado', label: 'Estado del sistema' },
  { id: 'accesos', label: 'Accesos' },
  ...(LAB_ENABLED ? [{ id: 'laboratorio' as const, label: 'Laboratorio' }] : []),
  ...(DESIGN_ENABLED ? [{ id: 'diseno' as const, label: 'Diseño' }] : []),
];

/** Las pestañas que el rol permite (lo dice el servidor en `/auth/me`). */
function tabsFor(me: Me): { id: Tab; label: string }[] {
  return ALL_TABS.filter(
    (t) =>
      (me.sections as string[]).includes(t.id) ||
      // El laboratorio y la muestra de diseño son de desarrollo: solo superusuarios.
      ((t.id === 'laboratorio' || t.id === 'diseno') && me.role === 'superuser'),
  );
}

function tabFromHash(allowed: readonly Tab[]): Tab {
  const wanted = window.location.hash.replace(/^#\//, '');
  // #/geodatos y cualquier pestaña que el rol no tenga llevan a Explorar.
  return (allowed as string[]).includes(wanted) ? (wanted as Tab) : 'explorar';
}

function Screen({ tab }: { tab: Tab }) {
  if (tab === 'casos') return <CasesPage />;
  if (tab === 'conceptos') return <ConceptsPage />;
  if (tab === 'historial') return <HistoryPage />;
  if (tab === 'envios') return <DeliveriesPage />;
  if (tab === 'estado') return <SystemStatusPanel />;
  if (tab === 'accesos') return <AccessPage />;
  if (tab === 'diseno') return <DesignPreview />;
  if (tab === 'laboratorio') {
    return (
      <Suspense fallback={<p className="p-6 text-sm text-slate-400">Cargando el laboratorio…</p>}>
        <MuroLab />
      </Suspense>
    );
  }
  // Explorar no se dibuja aquí: App la deja montada (ver ExploreKeeper).
  return null;
}

/**
 * El globo de la marca: un aro, el ecuador, dos paralelos y un meridiano que
 * se angosta y se ensancha (`marca-meridiano`) para que parezca que gira.
 */
function BrandGlobe() {
  return (
    <span className="marca-simbolo" aria-hidden="true">
      <svg viewBox="0 0 32 32" width="26" height="26" fill="none" stroke="currentColor">
        <circle cx="16" cy="16" r="13" strokeWidth="1.8" />
        <path d="M3 16h26M5.5 9h21M5.5 23h21" strokeWidth="1.2" opacity="0.7" />
        <ellipse className="marca-meridiano" cx="16" cy="16" rx="6" ry="13" strokeWidth="1.6" />
      </svg>
    </span>
  );
}

/**
 * Botón para regresar al sistema principal de Oráculo (Benji, 09/11/2026).
 * Solo aparece si el servidor tiene ORACULO_URL.
 */
function OraculoLink() {
  const url = safeOraculoUrl(useAppConfig().data?.oraculo_url);
  if (!url) return null;
  return (
    <a
      href={url}
      className="hud-btn hud-btn--sm shrink-0 whitespace-nowrap bg-[#050d12]/85"
      title="Regresar al sistema principal de Oráculo"
      aria-label="Regresar a Oráculo"
    >
      ←<span className="hidden sm:inline"> Oráculo</span>
    </a>
  );
}

/** Mientras se sabe si hay sesión: el universo, sin nada encima. */
function Gate({ children }: { children?: ReactNode }) {
  return (
    <div className="relative h-dvh font-sans text-slate-100">
      <GraphicsBoundary fallback={null}>
        <SpaceBackground mode="drift" />
      </GraphicsBoundary>
      <div aria-hidden="true" className="velo-universo pointer-events-none absolute inset-0" />
      {children}
    </div>
  );
}

export function App() {
  const me = useMe();
  if (me.isPending) return <Gate />;
  if (me.error) {
    return (
      <Gate>
        <p role="alert" className="relative z-10 p-8 text-center text-sm text-rose-300">
          {me.error.message}
        </p>
      </Gate>
    );
  }
  if (!me.data) {
    return (
      <Gate>
        <LoginScreen />
      </Gate>
    );
  }
  // key: al cambiar de persona se monta todo de nuevo (nada de la anterior).
  return <Monitor key={me.data.username} me={me.data} />;
}

function Monitor({ me }: { me: Me }) {
  const tabs = tabsFor(me);
  const allowed = tabs.map((t) => t.id);
  const [tab, setTab] = useState<Tab>(() => tabFromHash(allowed));
  // Explorar se monta la primera vez que se visita y ya no se desmonta: cada
  // montaje creaba dos contextos 3D y volvía a subir la foto del cielo a la
  // tarjeta, y al ir y venir entre pestañas la Intel integrada se reiniciaba
  // (26/10/2026). Oculta, el globo deja de girar y no dibuja.
  const [exploreVisited, setExploreVisited] = useState(tab === 'explorar');
  if (tab === 'explorar' && !exploreVisited) setExploreVisited(true);

  // La luz que sigue al mouse en paneles y botones (styles/hud.css).
  useEffect(() => installSpotlight(), []);

  useEffect(() => {
    const onHashChange = () => {
      setTab(tabFromHash(tabsFor(me).map((t) => t.id)));
    };
    window.addEventListener('hashchange', onHashChange);
    return () => {
      window.removeEventListener('hashchange', onHashChange);
    };
  }, [me]);

  return (
    <div className="relative h-dvh font-sans text-slate-100">
      {/* El universo detrás de todas las pestañas (Benji, 26/10/2026). En
          Explorar sigue al globo; en las demás deriva solo, muy despacio. Si
          la tarjeta de video falla, queda el fondo negro del cuerpo. */}
      <GraphicsBoundary fallback={null}>
        <SpaceBackground mode={tab === 'explorar' ? 'camera' : 'drift'} />
      </GraphicsBoundary>
      {/* Fuera de Explorar, un velo oscuro con aurora cian para que el texto
          se lea sobre las estrellas (ver .velo-universo). */}
      <div
        aria-hidden="true"
        className={`velo-universo pointer-events-none absolute inset-0 transition-opacity duration-700 ${
          tab === 'explorar' ? 'opacity-0' : 'opacity-100'
        }`}
      />
      {/* Encabezado sin fondo y centrado, sobre las estrellas (Benji, 26/10/2026):
          la marca de OSINT Oráculo y las pestañas en un solo grupo al centro.
          En celular (Benji, 11/11/2026) son dos renglones: arriba la marca con
          «Oráculo» y la sesión; abajo las pestañas, que se deslizan. El orden
          lo dan las clases order-*, sin repetir componentes. */}
      <header className="encabezado pointer-events-none absolute inset-x-0 top-0 z-30 flex h-[var(--header-h)] items-center justify-center px-3 sm:px-4">
        <div className="pointer-events-auto flex w-full min-w-0 max-w-full flex-col gap-1.5 sm:w-auto sm:flex-row sm:items-center sm:justify-center sm:gap-7">
          {/* Celular: este renglón junta la marca con «Oráculo» y la sesión.
              En pantallas anchas desaparece (sm:contents) y cada pieza toma
              su lugar en la fila con su order-*. */}
          <div className="flex w-full min-w-0 items-center justify-between gap-2 sm:contents">
            <a
              href="#/explorar"
              className="marca-signal min-w-0 shrink rounded-lg focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-sky-400 sm:order-1"
            >
              <BrandGlobe />
              <span className="flex min-w-0 flex-col items-start">
                <h1 className="marca-nombre">Monitor de Noticias</h1>
                <span className="marca-linea">
                  <span className="marca-linea-texto">Oráculo · Noticias geolocalizadas</span>
                  <span className="marca-scan" aria-hidden="true" />
                </span>
              </span>
            </a>
            <div className="flex shrink-0 items-center gap-2 sm:order-4 sm:gap-7">
              <OraculoLink />
              <UserCapsule me={me} />
            </div>
          </div>
          {/* Separador vertical que se desvanece arriba y abajo. */}
          <span
            aria-hidden="true"
            className="hidden h-8 w-px bg-gradient-to-b from-transparent via-sky-400/45 to-transparent sm:order-2 sm:block"
          />
          <div className="w-full min-w-0 sm:order-3 sm:w-auto">
            <HudTabs tabs={tabs} active={tab} label="Secciones" />
          </div>
        </div>
      </header>
      {/* Explorar empieza arriba de todo: el universo y el globo siguen detrás
          del encabezado. Las demás pestañas empiezan debajo de él, para que su
          contenido no pase por detrás del texto al desplazarse. */}
      <main
        className={`absolute inset-x-0 bottom-0 overflow-auto ${
          tab === 'explorar' ? 'top-0' : 'top-[var(--header-h)]'
        }`}
      >
        {exploreVisited && (
          <div hidden={tab !== 'explorar'} className="h-full">
            <ExplorePage active={tab === 'explorar'} />
          </div>
        )}
        <Screen tab={tab} />
      </main>
    </div>
  );
}
