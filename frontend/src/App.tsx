/**
 * Componente raíz: encabezado, menú de secciones a la izquierda y la pantalla activa.
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
 * Forma de Oráculo core (ADR-0108): a la izquierda su logo, «ORÁCULO» y la
 * etiqueta «NOTICIAS» (el logo regresa al Hub de Oráculo); al centro las
 * pestañas; a la derecha la sesión. Fuera de Explorar, el fondo es la
 * cuadrícula y la constelación de Oráculo, y abajo al centro va el chip
 * «Estado del sistema».
 *
 * Con `?laboratorio` en la URL aparece además "Laboratorio" (#/laboratorio):
 * el laboratorio del muro de la Fase 9.1 (ADR-0102). Se carga aparte, solo al
 * abrirlo, para no pesar en Explorar.
 */
import { lazy, type ReactNode, Suspense, useEffect, useState } from 'react';

import oraculoIcon from './assets/brand/oraculo-icon.svg';
import { AccessPage } from './components/Access/AccessPage';
import { LoginScreen } from './components/Auth/LoginScreen';
import { UserCapsule } from './components/Auth/UserCapsule';
import { CasesPage } from './components/Cases/CasesPage';
import { ConceptsPage } from './components/Concepts/ConceptsPage';
import { ExplorePage } from './components/Explore/ExplorePage';
import { GraphicsBoundary } from './components/Explore/GraphicsBoundary';
import { Constellation } from './components/Space/Constellation';
import { SpaceBackground } from './components/Space/SpaceBackground';
import { DesignPreview } from './components/DesignPreview/DesignPreview';
import { HistoryPage } from './components/History/HistoryPage';
import { DeliveriesPage } from './components/Deliveries/DeliveriesPage';
import { StatusChip } from './components/SystemStatus/StatusChip';
import { SystemStatusPanel } from './components/SystemStatus/SystemStatusPanel';
import { HudDock, type HudDockItem } from './components/ui/HudDock';
import { useAppConfig } from './hooks/useAppConfig';
import { useMe } from './hooks/useAuth';
import type { Me, Section } from './services/auth';
import { safeOraculoUrl } from './services/appConfig';

type Tab = Section | 'laboratorio' | 'diseno';

const MuroLab = lazy(() => import('./lab/MuroLab'));
// El laboratorio es solo para desarrollo: se pide a propósito en la URL.
const LAB_ENABLED = new URLSearchParams(window.location.search).has('laboratorio');
// La muestra del diseño nuevo (27/10/2026): solo con ?diseno en la URL.
const DESIGN_ENABLED = new URLSearchParams(window.location.search).has('diseno');

// Cada sección con su icono y el nombre que cabe debajo de él en el menú.
const ALL_TABS: HudDockItem<Tab>[] = [
  { id: 'explorar', label: 'Explorar', short: 'Explorar', icon: 'public' },
  { id: 'casos', label: 'Casos', short: 'Casos', icon: 'folder_shared' },
  { id: 'conceptos', label: 'Conceptos', short: 'Conceptos', icon: 'label' },
  { id: 'historial', label: 'Historial', short: 'Historial', icon: 'history' },
  { id: 'envios', label: 'Envíos', short: 'Envíos', icon: 'send' },
  { id: 'estado', label: 'Estado del sistema', short: 'Estado', icon: 'monitor_heart' },
  { id: 'accesos', label: 'Accesos', short: 'Accesos', icon: 'manage_accounts' },
  ...(LAB_ENABLED
    ? [{ id: 'laboratorio' as const, label: 'Laboratorio', short: 'Lab', icon: 'science' as const }]
    : []),
  ...(DESIGN_ENABLED
    ? [{ id: 'diseno' as const, label: 'Diseño', short: 'Diseño', icon: 'palette' as const }]
    : []),
];

/** Las secciones que el rol permite (lo dice el servidor en `/auth/me`). */
function tabsFor(me: Me): HudDockItem<Tab>[] {
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
 * La marca de Oráculo core (ADR-0108): su logo, «ORÁCULO» y la etiqueta
 * «NOTICIAS» con el nombre del módulo. Si el servidor tiene ORACULO_URL, el
 * logo regresa al Hub de Oráculo (Benji, 09/11/2026; antes era el botón
 * «← Oráculo»).
 */
function OraculoBrand() {
  const url = safeOraculoUrl(useAppConfig().data?.oraculo_url);
  const logo = (
    <>
      <span className="oraculo-icon-box" aria-hidden="true">
        <img src={oraculoIcon} alt="" width="50" height="50" />
      </span>
      <span className="oraculo-logo-text">Oráculo</span>
    </>
  );
  return (
    <div className="flex min-w-0 items-center gap-3">
      {url ? (
        <a
          href={url}
          className="oraculo-logo"
          aria-label="Regresar a Oráculo"
          title="Regresar al sistema principal de Oráculo"
        >
          {logo}
        </a>
      ) : (
        <span className="oraculo-logo">{logo}</span>
      )}
      <h1 className="hud-chip">Noticias</h1>
    </div>
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

  useEffect(() => {
    const onHashChange = () => {
      setTab(tabFromHash(tabsFor(me).map((t) => t.id)));
    };
    window.addEventListener('hashchange', onHashChange);
    return () => {
      window.removeEventListener('hashchange', onHashChange);
    };
  }, [me]);

  const outsideExplore = tab !== 'explorar';
  return (
    <div className="relative h-dvh font-sans text-slate-100">
      {/* En Explorar, el universo que sigue al globo. Se monta al visitarla y
          se queda, como el globo; fuera de ella no se ve ni dibuja. Si la
          tarjeta de video falla, queda el fondo negro del cuerpo. */}
      {exploreVisited && (
        <GraphicsBoundary fallback={null}>
          <SpaceBackground mode="camera" />
        </GraphicsBoundary>
      )}
      {/* Fuera de Explorar, el fondo de Oráculo (ADR-0108): la cuadrícula
          (ver .fondo-oraculo) y la constelación, que solo se monta ahí. */}
      <div
        aria-hidden="true"
        className={`fondo-oraculo pointer-events-none absolute inset-0 transition-opacity duration-700 ${
          outsideExplore ? 'opacity-100' : 'opacity-0'
        }`}
      >
        {outsideExplore && <Constellation />}
      </div>
      {/* El encabezado de Oráculo: la marca a la izquierda y la sesión a la
          derecha. El menú de secciones (HudDock) es la barra vertical de la
          izquierda; en el HTML vive aquí porque en celular (Benji, 11/11/2026)
          es el segundo renglón del encabezado y se desliza. No atrapa clics
          fuera de sus piezas (en Explorar el globo sigue detrás). */}
      <header className="encabezado pointer-events-none absolute inset-x-0 top-0 z-30 flex h-[var(--header-h)] items-center px-3 sm:px-5">
        <div className="flex w-full min-w-0 flex-col gap-1.5 sm:flex-row sm:items-center sm:gap-5">
          {/* Celular: este renglón junta la marca y la sesión. En pantallas
              anchas desaparece (sm:contents) y cada pieza toma su lugar. */}
          <div className="flex w-full min-w-0 items-center justify-between gap-2 sm:contents">
            <div className="pointer-events-auto min-w-0 shrink sm:order-1">
              <OraculoBrand />
            </div>
            <div className="pointer-events-auto shrink-0 sm:order-3">
              <UserCapsule me={me} />
            </div>
          </div>
          <div className="flex w-full min-w-0 justify-center *:pointer-events-auto sm:order-2 sm:flex-1">
            <HudDock items={tabs} active={tab} label="Secciones" />
          </div>
        </div>
      </header>
      {/* Explorar empieza arriba de todo: el universo y el globo siguen detrás
          del encabezado y del menú (sus paneles se corren solos, ver
          ExplorePage). Las demás pestañas empiezan debajo del encabezado y a
          la derecha del menú (--dock-w), para que nada pase por detrás. */}
      <main
        className={`absolute inset-x-0 bottom-0 overflow-auto ${
          outsideExplore ? 'top-[var(--header-h)] pb-16 pl-[var(--dock-w)]' : 'top-0'
        }`}
      >
        {exploreVisited && (
          <div hidden={tab !== 'explorar'} className="h-full">
            <ExplorePage active={tab === 'explorar'} />
          </div>
        )}
        <Screen tab={tab} />
      </main>
      {/* El pie de Oráculo; en Explorar esa franja es de «Consulta activa». */}
      {outsideExplore && <StatusChip linkToStatus={allowed.includes('estado')} />}
    </div>
  );
}
