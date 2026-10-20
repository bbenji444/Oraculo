/**
 * Componente raíz: encabezado con pestañas y la pantalla activa.
 *
 * Pestañas: "Explorar" (globo, búsqueda y resultados, F6), "Conceptos"
 * (administración y "Probar concepto", F2), "Historial" (búsquedas anteriores,
 * F6) y "Estado del sistema" (F0). La pestaña vive en la URL (#/explorar,
 * #/conceptos, #/historial, #/estado) para que se pueda compartir o recargar
 * sin perderla; #/geodatos sigue llevando a Explorar. No hace llamadas HTTP.
 */
import { useEffect, useState } from 'react';

import { ConceptsPage } from './components/Concepts/ConceptsPage';
import { ExplorePage } from './components/Explore/ExplorePage';
import { HistoryPage } from './components/History/HistoryPage';
import { SystemStatusPanel } from './components/SystemStatus/SystemStatusPanel';

type Tab = 'explorar' | 'conceptos' | 'historial' | 'estado';

const TABS: { id: Tab; label: string }[] = [
  { id: 'explorar', label: 'Explorar' },
  { id: 'conceptos', label: 'Conceptos' },
  { id: 'historial', label: 'Historial' },
  { id: 'estado', label: 'Estado del sistema' },
];

function tabFromHash(): Tab {
  const hash = window.location.hash;
  if (hash === '#/estado') return 'estado';
  if (hash === '#/conceptos') return 'conceptos';
  if (hash === '#/historial') return 'historial';
  return 'explorar';
}

function Screen({ tab }: { tab: Tab }) {
  if (tab === 'conceptos') return <ConceptsPage />;
  if (tab === 'historial') return <HistoryPage />;
  if (tab === 'estado') return <SystemStatusPanel />;
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
    <div className="flex h-dvh flex-col bg-slate-950 font-sans text-slate-100">
      <header className="z-30 border-b border-slate-800/80 bg-slate-950/90 backdrop-blur">
        {/* En celular las pestañas bajan a su propio renglón y se deslizan si no caben. */}
        <div className="flex flex-wrap items-center gap-x-6 gap-y-2 px-4 py-2.5 sm:flex-nowrap sm:px-6 sm:py-3">
          <div className="flex shrink-0 items-center gap-3">
            <img src="/globo.svg" alt="" className="size-7" />
            <div>
              <h1 className="text-base font-semibold leading-tight tracking-tight">
                Monitor de Noticias
              </h1>
              <p className="hidden text-xs text-slate-400 sm:block">
                Noticias geolocalizadas sobre México
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
                    ? 'bg-slate-800 text-slate-50'
                    : 'text-slate-400 hover:bg-slate-900 hover:text-slate-200'
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
