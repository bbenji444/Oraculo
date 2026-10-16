/**
 * Componente raíz: encabezado con pestañas y la pantalla activa.
 *
 * Pestañas: "Geodatos" (globo con el catálogo de regiones, F1), "Conceptos"
 * (administración y "Probar concepto", F2) y "Estado del sistema" (F0). La
 * pestaña vive en la URL (#/geodatos, #/conceptos, #/estado) para que se pueda
 * compartir o recargar sin perderla. No hace llamadas HTTP.
 */
import { useEffect, useState } from 'react';

import { ConceptsPage } from './components/Concepts/ConceptsPage';
import { GeoExplorer } from './components/GeoExplorer/GeoExplorer';
import { SystemStatusPanel } from './components/SystemStatus/SystemStatusPanel';

type Tab = 'geodatos' | 'conceptos' | 'estado';

const TABS: { id: Tab; label: string }[] = [
  { id: 'geodatos', label: 'Geodatos' },
  { id: 'conceptos', label: 'Conceptos' },
  { id: 'estado', label: 'Estado del sistema' },
];

function tabFromHash(): Tab {
  const hash = window.location.hash;
  if (hash === '#/estado') return 'estado';
  if (hash === '#/conceptos') return 'conceptos';
  return 'geodatos';
}

function Screen({ tab }: { tab: Tab }) {
  if (tab === 'conceptos') return <ConceptsPage />;
  if (tab === 'estado') return <SystemStatusPanel />;
  return <GeoExplorer />;
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
        <div className="flex items-center gap-6 px-4 py-3 sm:px-6">
          <div className="flex items-center gap-3">
            <img src="/globo.svg" alt="" className="size-7" />
            <div>
              <h1 className="text-base font-semibold leading-tight tracking-tight">
                Monitor de Noticias
              </h1>
              <p className="text-xs text-slate-400">Noticias geolocalizadas sobre México</p>
            </div>
          </div>
          <nav aria-label="Secciones" className="flex gap-1">
            {TABS.map((item) => (
              <a
                key={item.id}
                href={`#/${item.id}`}
                aria-current={tab === item.id ? 'page' : undefined}
                className={`rounded-lg px-3 py-1.5 text-sm transition-colors focus-visible:outline-2 focus-visible:outline-sky-400 ${
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
