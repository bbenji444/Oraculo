/**
 * Componente raíz de la interfaz.
 *
 * En F0 solo muestra el encabezado; el globo y el panel de búsqueda llegan
 * en F6. No hace llamadas HTTP (eso vive en src/services/).
 */
export function App() {
  return (
    <main className="min-h-screen bg-slate-950 text-slate-100">
      <header className="border-b border-slate-800 px-6 py-4">
        <h1 className="text-lg font-semibold tracking-tight">Monitor de Noticias</h1>
        <p className="text-sm text-slate-400">Noticias geolocalizadas sobre México</p>
      </header>
    </main>
  );
}
