/**
 * Pestaña «God's Eye» (27/10/2026): la entrada al proyecto God's Eye View.
 *
 * Benji pidió verlo «tal cual como aparece en el proyecto de GitHub», con su
 * propio globo, desde una sección del encabezado, para analizarlo antes de
 * decidir cómo integrarlo. Corre en su propio servidor (scripts/dev/gods_eye.sh)
 * y aquí no se adapta nada.
 *
 * Por qué se abre en su propia pestaña y no dentro del monitor: God's Eye View
 * no se deja mostrar en un iframe (X-Frame-Options: DENY), a propósito, porque
 * su servidor guarda llaves de API y una página que lo enmarque podría operar
 * su panel. Su «modo embed» oficial (`?embed=1`) sí se deja, pero muestra solo
 * el globo, sin paneles: no sería «tal cual». Quitarle esa protección sería
 * modificar su código.
 *
 * No hace: no le pasa datos del monitor ni lee los suyos.
 */
import { ExternalLink } from '../ExternalLink';
import { useGodsEye } from '../../hooks/useGodsEye';
import { godsEyeUrl } from '../../services/godsEye';

const REPOSITORY = 'https://github.com/bilawalsidhu/gods-eye-view';

/** Qué se puede ver sin llaves de API (su `npm run doctor`, 27/10/2026). */
const KEYLESS = [
  'Globo 3D con imagen satelital de Esri y relieve',
  'Vuelos en vivo (OpenSky, acceso anónimo con límite)',
  'Satélites y la Estación Espacial (CelesTrak)',
  'Sismos (USGS), misiones espaciales y cámaras públicas',
  'Tráfico simulado y modos de visión (nocturna, térmica, CRT)',
];

export function GodsEyePage() {
  const url = godsEyeUrl(window.location);
  const status = useGodsEye(url);
  return (
    <div className="mx-auto max-w-2xl px-4 py-10">
      <p className="font-display text-xs tracking-[0.3em] text-sky-300/80">MÓDULO EN EVALUACIÓN</p>
      <h2 className="mt-2 font-display text-2xl tracking-wider text-sky-50">GOD&apos;S EYE VIEW</h2>
      <p className="mt-3 text-sm leading-relaxed text-slate-300">
        El proyecto completo, tal cual su{' '}
        <ExternalLink href={REPOSITORY} className="text-sky-300 hover:underline">
          repositorio en GitHub
        </ExternalLink>{' '}
        (Bilawal Sidhu, código MIT), con su propio globo. Todavía no está integrado al monitor: se
        abre en su propia pestaña porque, por seguridad, no se deja mostrar dentro de otra página.
      </p>

      <div className="mt-6 rounded-xl border border-sky-400/20 bg-black/50 p-5">
        {status.data === true ? (
          <>
            <p className="flex items-center gap-2 text-sm text-emerald-300">
              <span className="size-2 rounded-full bg-emerald-400 shadow-[0_0_8px_rgb(52_211_153/0.9)]" />
              Corriendo en {url}
            </p>
            <ExternalLink
              href={url}
              className="mt-4 inline-block rounded-lg bg-sky-500/20 px-5 py-2.5 font-display text-sm tracking-wider text-sky-50 ring-1 ring-sky-400/40 hover:bg-sky-500/30"
              title="Se abre en una pestaña nueva"
            >
              ENTRAR A GOD&apos;S EYE VIEW
            </ExternalLink>
          </>
        ) : status.data === false ? (
          <>
            <p className="text-sm text-amber-200">God&apos;s Eye View no está corriendo.</p>
            <p className="mt-2 text-sm text-slate-300">
              Se levanta junto con el monitor. Desde PowerShell, en la carpeta del proyecto:
            </p>
            <pre className="mt-3 rounded-md bg-black/60 px-3 py-2 text-sky-200">wsl make up</pre>
            <p className="mt-3 text-xs text-slate-400">
              Si nunca se instaló: <code className="text-sky-200">wsl make gev-instalar</code>. Esta
              pantalla lo vuelve a buscar sola cada 5 segundos.
            </p>
          </>
        ) : (
          <p className="text-sm text-slate-400">Buscando God&apos;s Eye View…</p>
        )}
      </div>

      <h3 className="mt-8 text-sm font-medium text-slate-200">Funciona sin llaves</h3>
      <ul className="mt-2 list-inside list-disc space-y-1 text-sm text-slate-300">
        {KEYLESS.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
      <p className="mt-4 text-xs leading-relaxed text-slate-400">
        Barcos (AISStream), incendios (NASA FIRMS), voz (OpenAI) y vista de calle de Google piden
        llave propia; se agregan dentro de God&apos;s Eye View, en el chip de abajo a la derecha
        («Provider Settings»). Algunos datos que trae incluidos no son de uso comercial (cables
        submarinos de TeleGeography): ver su LICENSE antes de llevarlo a producción.
      </p>
    </div>
  );
}
