/**
 * Red de seguridad para lo que se dibuja con la tarjeta de video (el globo y el
 * fondo del espacio).
 *
 * Por qué: el 26/10/2026 Benji descargó el PDF y la pantalla quedó en blanco.
 * La tarjeta de video se reinició y Chrome bloqueó los gráficos 3D de la página
 * («Web page caused context loss and was blocked»). Después, al crear el globo,
 * MapLibre y three.js lanzan un error que nadie atrapaba, y React desmontaba la
 * aplicación entera. Con esta red solo se cae lo que se dibuja: el panel, la
 * cronología y el PDF siguen funcionando, y en lugar del globo sale `fallback`.
 *
 * Lo usa `ExplorePage`. No hace: no reintenta solo (recargar la página es lo
 * que devuelve los gráficos cuando Chrome los bloqueó).
 */
import { Component, type ErrorInfo, type ReactNode } from 'react';

interface GraphicsBoundaryProps {
  /** Lo que se muestra si lo de adentro falla. */
  fallback: ReactNode;
  children: ReactNode;
}

interface GraphicsBoundaryState {
  failed: boolean;
}

/** Atrapa los errores al dibujar (por ejemplo, sin WebGL) y muestra `fallback`. */
export class GraphicsBoundary extends Component<GraphicsBoundaryProps, GraphicsBoundaryState> {
  override state: GraphicsBoundaryState = { failed: false };

  static getDerivedStateFromError(): GraphicsBoundaryState {
    return { failed: true };
  }

  override componentDidCatch(error: Error, info: ErrorInfo): void {
    // Queda en la consola para diagnosticar; la pantalla ya muestra el aviso.
    console.error('No se pudieron dibujar los gráficos 3D', error, info.componentStack);
  }

  override render(): ReactNode {
    return this.state.failed ? this.props.fallback : this.props.children;
  }
}

/** Aviso en lugar del globo, con la salida: recargar la página. */
export function GlobeUnavailable() {
  return (
    <div className="absolute inset-0 flex items-center justify-center p-6">
      <div
        role="alert"
        className="max-w-sm rounded-2xl border border-white/10 bg-slate-950/80 p-5 text-center shadow-2xl backdrop-blur-md"
      >
        <p className="text-sm font-semibold text-slate-100">No se pudo dibujar el globo</p>
        <p className="mt-2 text-xs leading-relaxed text-slate-300">
          El navegador apagó los gráficos 3D de la página. Suele pasar cuando la tarjeta de video se
          queda sin memoria, por ejemplo con muchas pestañas o PDF abiertos. La búsqueda, la
          cronología y el PDF siguen funcionando.
        </p>
        <button
          type="button"
          onClick={() => {
            window.location.reload();
          }}
          className="mt-4 rounded-xl bg-gradient-to-r from-sky-500 to-cyan-400 px-4 py-2 text-sm font-semibold text-slate-950 hover:brightness-110 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-300"
        >
          Recargar
        </button>
      </div>
    </div>
  );
}
