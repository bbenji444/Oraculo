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
import { HistoryPage } from './components/History/HistoryPage';
import { SystemStatusPanel } from './components/SystemStatus/SystemStatusPanel';

type Tab = 'explorar' | 'casos' | 'conceptos' | 'historial' | 'estado' | 'laboratorio';

const MuroLab = lazy(() => import('./lab/MuroLab'));
// El laboratorio es solo para desarrollo: se pide a propósito en la URL.
const LAB_ENABLED = new URLSearchParams(window.location.search).has('laboratorio');

const TABS: { id: Tab; label: string }[] = [
  { id: 'explorar', label: 'Explorar' },
  { id: 'casos', label: 'Casos' },
  { id: 'conceptos', label: 'Conceptos' },
  { id: 'historial', label: 'Historial' },
  { id: 'estado', label: 'Estado del sistema' },
  ...(LAB_ENABLED ? [{ id: 'laboratorio' as const, label: 'Laboratorio' }] : []),
];

function tabFromHash(): Tab {
  const hash = window.location.hash;
  if (hash === '#/laboratorio' && LAB_ENABLED) return 'laboratorio';
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
  if (tab === 'laboratorio') {
    return (
      <Suspense fallback={<p className="p-6 text-sm text-slate-400">Cargando el laboratorio…</p>}>
        <MuroLab />
      </Suspense>
    );
  }
  return <ExplorePage />;
}

export function App() {
  const [tab, setTab] = useState<Tab>(tabFromHash);

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
    <div className="flex h-dvh flex-col font-sans text-slate-100">
      <header className="z-30 border-b border-sky-400/20 bg-slate-950/85 shadow-[0_1px_18px_rgb(0_210_255/0.08)] backdrop-blur-md">
        {/* En celular las pestañas bajan a su propio renglón y se deslizan si no caben. */}
        <div className="flex flex-wrap items-center gap-x-6 gap-y-2 px-4 py-2.5 sm:flex-nowrap sm:px-6 sm:py-3">
          <div className="flex shrink-0 items-center gap-3">
            <img
              src="/globo.svg"
              alt=""
              className="size-7 drop-shadow-[0_0_10px_rgb(0_210_255/0.45)]"
            />
            <div>
              {/* Marca homologada con OSINT Oráculo (F12.7a): Orbitron con brillo cian. */}
              <h1 className="marca-oraculo text-[15px] font-bold leading-tight text-sky-50">
                Monitor de Noticias
              </h1>
              <p className="hidden text-[11px] tracking-wide text-slate-400 sm:block">
                Oráculo · Noticias geolocalizadas sobre México
              </p>
            </div>
          </div>
          <nav
            aria-label="Secciones"
            className="flex w-full min-w-0 gap-0.5 overflow-x-auto sm:w-auto sm:gap-1"
          >
            {TABS.map((item) => (
              <a
                key={item.id}
                href={`#/${item.id}`}
                aria-current={tab === item.id ? 'page' : undefined}
                className={`shrink-0 whitespace-nowrap rounded-lg px-2 py-1.5 text-[13px] sm:px-3 sm:text-sm transition-colors focus-visible:outline-2 focus-visible:outline-sky-400 ${
                  tab === item.id
                    ? 'bg-sky-400/10 text-sky-100 shadow-glow'
                    : 'text-slate-400 hover:bg-sky-400/5 hover:text-slate-100'
                }`}
              >
                {item.label}
              </a>
            ))}
          </nav>
        </div>
      </header>
      <main className="min-h-0 flex-1 overflow-auto">
        <Screen tab={tab} />
      </main>
    </div>
  );
}
