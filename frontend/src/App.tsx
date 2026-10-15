/**
 * Componente raíz de la interfaz.
 *
 * En F0 muestra el estado del sistema; el globo y el panel de búsqueda
 * llegan en F6. No hace llamadas HTTP (eso vive en src/services/).
 */
import { SystemStatusPanel } from './components/SystemStatus/SystemStatusPanel';

export function App() {
  return (
    <div className="min-h-screen bg-slate-950 font-sans text-slate-100">
      <header className="border-b border-slate-800/80 bg-slate-950/80 backdrop-blur">
        <div className="mx-auto flex max-w-4xl items-center gap-3 px-6 py-4">
          <img src="/globo.svg" alt="" className="size-7" />
          <div>
            <h1 className="text-lg font-semibold tracking-tight">Monitor de Noticias</h1>
            <p className="text-sm text-slate-400">Noticias geolocalizadas sobre México</p>
          </div>
        </div>
      </header>
      <main>
        <SystemStatusPanel />
      </main>
    </div>
  );
}
