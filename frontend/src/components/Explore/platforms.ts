/**
 * Plataformas de las notas (ADR-0117): dónde se publicó cada una, para
 * fraccionar los resultados como Google («Todo · Noticias · Facebook · X…»)
 * y filtrar por una sola.
 *
 * El servidor dice la plataforma de cada nota (`Article.platform`) con una
 * sola regla, la misma para la pantalla, el reporte y el CSV. Aquí solo se
 * nombra, se cuenta y se elige; si una respuesta vieja no la trae, la nota se
 * toma como noticia.
 *
 * No hace: no adivina la plataforma por la URL (eso lo hace el servidor) ni
 * dibuja (eso es `PlatformMark.tsx` y `Mando/PlatformTabs.tsx`).
 */
import type { Article, Platform } from '../../services/searches';
import type { IconName } from '../ui/Icon';

export interface PlatformInfo {
  id: Platform;
  /** Nombre en pantalla, en español. */
  label: string;
  /**
   * Icono de Material Icons, o `null` para X: la letra no trae su logo y va
   * como una «X» en negritas (`PlatformMark`). Tampoco trae los de YouTube e
   * Instagram: van con el botón de video y la cámara, que se reconocen igual.
   */
  icon: IconName | null;
  /** Color de la marca en «r g b» (para `--cat` en styles/mando.css). */
  tone: string;
}

/**
 * Las plataformas en el orden de las pestañas: primero las noticias (casi
 * todo lo que trae una búsqueda) y al final «Otros sitios».
 *
 * Los colores son los de cada marca, aclarados donde hacía falta para leerse
 * sobre el fondo oscuro: Facebook #1877F2, YouTube #FF3040 (el #FF0000 se
 * veía café), Instagram #E1306C, TikTok #25F4EE, Reddit #FF4500 y Telegram
 * #2AABEE. X va en gris claro (su marca es blanca y negra), las noticias en
 * el cian de la consola y los otros sitios en gris.
 */
const WEB: PlatformInfo = {
  id: 'web',
  label: 'Otros sitios',
  icon: 'language',
  tone: '148 163 184',
};

export const PLATFORMS: readonly PlatformInfo[] = [
  { id: 'news', label: 'Noticias', icon: 'newspaper', tone: '0 210 255' },
  { id: 'facebook', label: 'Facebook', icon: 'facebook', tone: '24 119 242' },
  { id: 'x', label: 'X', icon: null, tone: '226 232 240' },
  { id: 'youtube', label: 'YouTube', icon: 'smart_display', tone: '255 48 64' },
  { id: 'instagram', label: 'Instagram', icon: 'photo_camera', tone: '225 48 108' },
  { id: 'tiktok', label: 'TikTok', icon: 'tiktok', tone: '37 244 238' },
  { id: 'reddit', label: 'Reddit', icon: 'reddit', tone: '255 69 0' },
  { id: 'telegram', label: 'Telegram', icon: 'telegram', tone: '42 171 238' },
  WEB,
];

const BY_ID = new Map<string, PlatformInfo>(PLATFORMS.map((p) => [p.id, p]));
// Separador entre la plataforma y quien publicó, el mismo del servidor
// (`LABEL_SEPARATOR` en backend/app/domain/platforms.py): «X · ivillasenor».
const LABEL_SEPARATOR = ' · ';

/**
 * Dónde se publicó una nota.
 *
 * @param article Nota de la API.
 * @returns Su plataforma; `news` si la respuesta no la trae (es de antes del
 *   18/11/2026) y `web` si trae una que esta pantalla todavía no conoce.
 * @example platformOf({ platform: 'facebook' }) // 'facebook'
 * @example platformOf({}) // 'news'
 */
export function platformOf(article: Pick<Article, 'platform'>): Platform {
  const value = article.platform;
  if (!value) return 'news';
  return BY_ID.has(value) ? value : 'web';
}

/**
 * Nombre, icono y color de una plataforma.
 *
 * @param platform Plataforma de la nota (ya resuelta con `platformOf`).
 * @returns Su nombre en pantalla, icono y color; los de «Otros sitios» si no se conoce.
 * @example platformInfo('youtube').label // 'YouTube'
 */
export function platformInfo(platform: Platform): PlatformInfo {
  return BY_ID.get(platform) ?? WEB;
}

/**
 * Si la nota es de un medio de noticias (las que no llevan marca de plataforma).
 *
 * @param platform Plataforma de la nota (ya resuelta con `platformOf`).
 * @returns `true` solo para `news`.
 */
export function isNewsPlatform(platform: Platform): boolean {
  return platform === 'news';
}

/** Una plataforma con cuántas notas trae. */
export interface PlatformCount extends PlatformInfo {
  count: number;
}

/**
 * Las plataformas presentes en las notas, con cuántas trae cada una, en el
 * orden fijo de `PLATFORMS` (no de más a menos: así no brincan de lugar al
 * cambiar otro filtro).
 *
 * @param articles Notas a contar.
 * @returns Solo las que tienen al menos una nota.
 * @example platformsIn(notas) // [{ id: 'news', count: 35, … }, { id: 'facebook', count: 5, … }]
 */
export function platformsIn(articles: readonly Pick<Article, 'platform'>[]): PlatformCount[] {
  const counts = new Map<Platform, number>();
  for (const article of articles) {
    const platform = platformOf(article);
    counts.set(platform, (counts.get(platform) ?? 0) + 1);
  }
  return PLATFORMS.filter((p) => counts.has(p.id)).map((p) => ({
    ...p,
    count: counts.get(p.id) ?? 0,
  }));
}

/**
 * Las pestañas de plataforma: las presentes y, aunque ya no tengan notas con
 * los demás filtros, las elegidas (para poder quitarlas).
 *
 * @param articles Notas con todos los filtros menos el de plataforma.
 * @param selected Plataformas elegidas.
 * @returns Las pestañas en el orden de pantalla, con su conteo (0 en las
 *   elegidas que ya no tienen notas).
 */
export function platformTabs(
  articles: readonly Pick<Article, 'platform'>[],
  selected: readonly Platform[],
): PlatformCount[] {
  const present = platformsIn(articles);
  const missing = selected.filter((id) => !present.some((p) => p.id === id));
  if (missing.length === 0) return present;
  return PLATFORMS.filter((p) => present.some((q) => q.id === p.id) || missing.includes(p.id)).map(
    (p) => present.find((q) => q.id === p.id) ?? { ...p, count: 0 },
  );
}

/**
 * Qué queda elegido al tocar una pestaña: solo esa; si ya era la única
 * elegida, ninguna («Todo»), como las pestañas de Google.
 *
 * @param selected Plataformas elegidas ahora.
 * @param platform La pestaña que se tocó.
 * @returns La plataforma que queda sola, o `null` para «Todo».
 * @example tabChoice(['facebook'], 'facebook') // null
 * @example tabChoice([], 'x') // 'x'
 */
export function tabChoice(selected: readonly Platform[], platform: Platform): Platform | null {
  return selected.length === 1 && selected[0] === platform ? null : platform;
}

/**
 * Texto del botón que abre el original.
 *
 * @param platform Plataforma de la nota.
 * @returns El texto del botón.
 * @example originalLinkLabel('facebook') // 'Ver publicación en Facebook'
 * @example originalLinkLabel('news') // 'Ver nota original'
 */
export function originalLinkLabel(platform: Platform): string {
  if (platform === 'news') return 'Ver nota original';
  if (platform === 'web') return 'Ver página original';
  return `Ver publicación en ${platformInfo(platform).label}`;
}

/**
 * Quién publicó la nota, sin repetir la plataforma que ya dice su marca.
 *
 * Google web dice «Facebook · Ignacio Gómez» o «X · ivillasenor», y Google
 * News dice «Facebook» a secas: junto a la marca de Facebook se leía dos
 * veces. Las noticias destacadas de Google web llegan como «Noticias ·
 * Quinta Fuerza» (backend/app/domain/platforms.py, `news_label`): también se
 * quita «Noticias · ».
 *
 * @param article Nota de la API.
 * @returns El medio o la cuenta; en medios y otros sitios sin nombre, su
 *   dominio; `null` si solo diría la plataforma.
 * @example outletName({ platform: 'x', source_name: 'X · ivillasenor', source_domain: 'x.com' }) // 'ivillasenor'
 */
export function outletName(
  article: Pick<Article, 'platform' | 'source_name' | 'source_domain'>,
): string | null {
  const platform = platformOf(article);
  const label = platformInfo(platform).label.toLowerCase();
  const raw = article.source_name?.trim() ?? '';
  const lower = raw.toLowerCase();
  const prefix = `${label}${LABEL_SEPARATOR}`;
  let name: string | null = raw || null;
  if (lower === label) name = null;
  else if (lower.startsWith(prefix)) name = raw.slice(prefix.length).trim() || null;
  if (name) return name;
  // En las redes el dominio (facebook.com) solo repetiría la plataforma.
  return isNewsPlatform(platform) || platform === 'web' ? article.source_domain : null;
}
