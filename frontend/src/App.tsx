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
 * Con `?laboratorio` en la URL aparece además "Laboratorio" (#/laboratorio):
 * el laboratorio del muro de la Fase 9.1 (ADR-0102). Se carga aparte, solo al
 * abrirlo, para no pesar en Explorar.
 */
import { lazy, Suspense, useEffect, useState } from 'react';

import { CasesPage } from './components/Cases/CasesPage';
import { ConceptsPage } from './components/Concepts/ConceptsPage';
import { ExplorePage } from './components/Explore/ExplorePage';
import { GraphicsBoundary } from './components/Explore/GraphicsBoundary';
import { SpaceBackground } from './components/Space/SpaceBackground';
import { DesignPreview } from './components/DesignPreview/DesignPreview';
import { HistoryPage } from './components/History/HistoryPage';
import { SystemStatusPanel } from './components/SystemStatus/SystemStatusPanel';
import { HudTabs } from './components/ui/HudTabs';
import { installSpotlight } from './ui/spotlight';

type Tab = 'explorar' | 'casos' | 'conceptos' | 'historial' | 'estado' | 'laboratorio' | 'diseno';

const MuroLab = lazy(() => import('./lab/MuroLab'));
// El laboratorio es solo para desarrollo: se pide a propósito en la URL.
const LAB_ENABLED = new URLSearchParams(window.location.search).has('laboratorio');
// La muestra del diseño nuevo (27/10/2026): solo con ?diseno en la URL.
const DESIGN_ENABLED = new URLSearchParams(window.location.search).has('diseno');

const TABS: { id: Tab; label: string }[] = [
  { id: 'explorar', label: 'Explorar' },
  { id: 'casos', label: 'Casos' },
  { id: 'conceptos', label: 'Conceptos' },
  { id: 'historial', label: 'Historial' },
  { id: 'estado', label: 'Estado del sistema' },
  ...(LAB_ENABLED ? [{ id: 'laboratorio' as const, label: 'Laboratorio' }] : []),
  ...(DESIGN_ENABLED ? [{ id: 'diseno' as const, label: 'Diseño' }] : []),
];

function tabFromHash(): Tab {
  const hash = window.location.hash;
  if (hash === '#/laboratorio' && LAB_ENABLED) return 'laboratorio';
  if (hash === '#/diseno' && DESIGN_ENABLED) return 'diseno';
  if (hash === '#/estado') return 'estado';
  if (hash === '#/casos') return 'casos';
  if (hash === '#/conceptos') return 'conceptos';
  if (hash === '#/historial') return 'historial';
  return 'explorar';
}

function Screen({ tab }: { tab: Tab }) {
  if (tab === 'casos') return <CasesPage />;
  if (tab === 'conceptos') return <ConceptsPage />;
  if (tab === 'historial') return <HistoryPage />;
  if (tab === 'estado') return <SystemStatusPanel />;
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

export function App() {
  const [tab, setTab] = useState<Tab>(tabFromHash);
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
      setTab(tabFromHash());
    };
    window.addEventListener('hashchange', onHashChange);
    return () => {
      window.removeEventListener('hashchange', onHashChange);
    };
  }, []);

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
          En celular las pestañas bajan a su propio renglón y se deslizan. */}
      <header className="pointer-events-none absolute inset-x-0 top-0 z-30 flex h-[var(--header-h)] items-center justify-center px-4">
        <div className="pointer-events-auto flex min-w-0 max-w-full flex-col items-center gap-2.5 sm:flex-row sm:gap-7">
          <a
            href="#/explorar"
            className="marca-signal shrink-0 rounded-lg focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-sky-400"
          >
            <BrandGlobe />
            <span className="flex flex-col items-start">
              <h1 className="marca-nombre">Monitor de Noticias</h1>
              <span className="marca-linea">
                <span className="marca-linea-texto">Oráculo · Noticias geolocalizadas</span>
                <span className="marca-scan" aria-hidden="true" />
              </span>
            </span>
          </a>
          {/* Separador vertical que se desvanece arriba y abajo. */}
          <span
            aria-hidden="true"
            className="hidden h-8 w-px bg-gradient-to-b from-transparent via-sky-400/45 to-transparent sm:block"
          />
          <HudTabs tabs={TABS} active={tab} label="Secciones" />
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
