/**
 * Reporte en pantalla (ADR-0111): «Ver reporte» y «Descargar PDF» junto al
 * expediente, y la ventana grande donde se lee el reporte sin descargarlo.
 *
 * El jefe de Benji pidió (17/11/2026) no tener que bajar un archivo cada vez
 * que quiere ver un reporte. La ventana muestra el mismo reporte que el PDF,
 * armado por la API (`GET /searches/{id}/report/view`), con índice, secciones
 * que se pliegan, filtro de noticias y cifras al pasar el mouse. El PDF se
 * sigue pudiendo bajar, desde el expediente o desde la ventana.
 *
 * El reporte va en un iframe con `sandbox`: no puede enviar formularios ni
 * cambiar la página del monitor. Lo que lo protege de una nota con algo raro
 * en el título es la política de la API: solo corre el script que lleva el
 * nonce de esa respuesta, y no puede pedir nada a ningún servidor. Los links a
 * las notas se abren en otra pestaña.
 *
 * No hace: no arma el reporte ni decide qué lleva (eso es la API).
 */
import { useCallback, useEffect, useId, useRef, useState } from 'react';
import { createPortal } from 'react-dom';

import { useDownloads } from '../../hooks/useDownloads';
import { reportViewUrl } from '../../services/reports';
import { GLASS } from '../Explore/ui';
import { Icon } from '../ui/Icon';

// Corre su script, abre los links en otra pestaña normal y conserva el origen
// del monitor. Sin `allow-same-origin` el navegador trata el reporte como de
// otro sitio y algunos lo bloquean (el del panel de Claude respondió
// ERR_BLOCKED_BY_CLIENT, 17/11/2026). Sin formularios ni navegación arriba.
const REPORT_SANDBOX =
  'allow-scripts allow-same-origin allow-popups allow-popups-to-escape-sandbox';

/**
 * Botón que baja el PDF; mientras se genera dice «Generando…».
 *
 * @param props.searchId Búsqueda terminada.
 */
function PdfButton({ searchId }: { searchId: string }) {
  const downloads = useDownloads(searchId);
  const running = downloads.running !== null;
  return (
    <span className="relative flex">
      <button
        type="button"
        disabled={running}
        onClick={() => {
          downloads.start('pdf');
        }}
        title="Baja el reporte en PDF. El primero de cada búsqueda cuesta ~0.0003 USD de IA; los siguientes, nada."
        className="hud-btn hud-btn--sm hud-btn--ghost w-full whitespace-nowrap"
      >
        <Icon name="download" />
        <span>{running ? 'Generando…' : 'Descargar PDF'}</span>
      </button>
      {downloads.error && (
        <span
          role="alert"
          className="absolute top-full right-0 z-10 mt-1 w-56 text-right text-[11px] text-rose-300"
        >
          {downloads.error.message}
        </span>
      )}
    </span>
  );
}

interface ReportWindowProps {
  searchId: string;
  title: string;
  onClose: () => void;
}

/**
 * Ventana casi de pantalla completa con el reporte. Se cierra con Esc, con
 * «×» o con un clic en el fondo oscuro.
 */
export function ReportWindow({ searchId, title, onClose }: ReportWindowProps) {
  const panelRef = useRef<HTMLDivElement>(null);
  const titleId = useId();
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    panelRef.current?.focus();
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => {
      window.removeEventListener('keydown', onKey);
    };
  }, [onClose]);

  return createPortal(
    <div
      className="mando-modal-backdrop fixed inset-0 z-[60] flex items-center justify-center p-2 sm:p-5"
      onPointerDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
        className={`${GLASS} mando-modal flex h-full w-full max-w-[1400px] flex-col bg-[#06121a]/[0.98] outline-none`}
      >
        <div className="flex items-center gap-2 px-4 py-2.5">
          <Icon name="description" className="text-lg text-sky-300" />
          <div className="min-w-0 flex-1">
            <h2 id={titleId} className="mando-kicker">
              Reporte
            </h2>
            <p className="truncate text-[13px] text-slate-200" title={title}>
              {title}
            </p>
          </div>
          <PdfButton searchId={searchId} />
          <button
            type="button"
            onClick={onClose}
            aria-label="Cerrar el reporte"
            title="Cerrar (Esc)"
            className="hud-icon-btn size-8 text-sm"
          >
            <Icon name="close" className="text-lg" />
          </button>
        </div>
        <div className="relative min-h-0 flex-1">
          {loading && (
            <p
              aria-live="polite"
              className="absolute inset-0 flex items-center justify-center gap-2 text-sm text-slate-300"
            >
              <span
                aria-hidden="true"
                className="size-4 animate-spin rounded-full border-2 border-slate-500 border-t-sky-300"
              />
              Armando el reporte…
            </p>
          )}
          <iframe
            title={`Reporte: ${title}`}
            src={reportViewUrl(searchId)}
            sandbox={REPORT_SANDBOX}
            onLoad={(event) => {
              setLoading(false);
              // Con el foco dentro del reporte, Esc también cierra la ventana.
              event.currentTarget.contentWindow?.addEventListener('keydown', (key) => {
                if (key.key === 'Escape') onClose();
              });
            }}
            className={`h-full w-full border-0 ${loading ? 'invisible' : ''}`}
          />
        </div>
      </div>
    </div>,
    document.body,
  );
}

/**
 * «Ver reporte» y «Descargar PDF», juntos en el renglón del expediente.
 *
 * @param props.searchId Búsqueda terminada.
 * @param props.title Concepto y región, para el encabezado de la ventana.
 */
export function ReportButtons({ searchId, title }: { searchId: string; title: string }) {
  const [open, setOpen] = useState(false);
  // Estable: si cambiara en cada render del expediente, la ventana volvería a
  // tomar el foco y se lo quitaría al reporte.
  const close = useCallback(() => {
    setOpen(false);
  }, []);
  return (
    <div role="group" aria-label="Reporte" className="grid grid-cols-2 gap-1.5">
      <button
        type="button"
        onClick={() => {
          setOpen(true);
        }}
        title="Abre el reporte aquí, sin descargar nada"
        className="hud-btn hud-btn--sm w-full whitespace-nowrap"
      >
        <Icon name="description" />
        <span>Ver reporte</span>
      </button>
      <PdfButton searchId={searchId} />
      {open && <ReportWindow searchId={searchId} title={title} onClose={close} />}
    </div>
  );
}
