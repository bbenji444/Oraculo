/**
 * Qué pasa cuando alguien genera **su propia** llave en «Accesos».
 *
 * Su llave anterior deja de servir en ese instante (ADR-0124) y la API
 * responde 401. Sin esto la pantalla lo sacaba antes de copiar la nueva
 * (Benji, 20/11/2026: «le di a generar una nueva llave y me sacó
 * inmediatamente»). Mientras el aviso está abierto se detiene la salida por
 * sesión terminada; el aviso se cierra solo a los pocos segundos y la
 * página se recarga, para que la sesión vieja no quede abierta («que se
 * cierre automáticamente, para que no haya tema»).
 *
 * Lo usan `ApiKeyRow` y `UserKeys`. No hace: no genera ni guarda la llave.
 */
import { useSignedInUsername } from '../../hooks/useAuth';
import { holdSession, page } from '../../services/http';

// Benji, 20/11/2026: «unos 10 segundos o algo, para que te dé tiempo de
// copiar la API nueva y después se cierra automáticamente».
export const OWN_KEY_CLOSE_SECONDS = 10;

export const OWN_KEY_HINT =
  'Es tu propia llave: pégala en tu usuario de Oráculo («Módulos externos»). Por seguridad, este aviso se cierra solo y tendrás que entrar de nuevo.';

/** Lo que hacen los botones de generar llave según de quién sea. */
export interface OwnKeyGuard {
  /** Si la llave es de quien usa la pantalla. */
  isSelf: boolean;
  /** Antes de pedirla: si es propia, detiene la salida por 401. */
  beforeIssue: () => void;
  /** Si falló: reanuda la salida normal. */
  onIssueError: () => void;
  /** Al cerrar el aviso: si es propia, reanuda y recarga la página. */
  afterClose: () => void;
}

/**
 * Prepara los pasos para generar la llave de `username` sin sacar a nadie a
 * medias.
 *
 * @param username Dueño de la llave que se va a generar.
 * @returns Los pasos para antes, en error y al cerrar el aviso.
 */
export function useOwnKeyGuard(username: string): OwnKeyGuard {
  const isSelf = useSignedInUsername() === username;
  return {
    isSelf,
    beforeIssue: () => {
      if (isSelf) holdSession(true);
    },
    onIssueError: () => {
      holdSession(false);
    },
    afterClose: () => {
      if (!isSelf) return;
      holdSession(false);
      page.reload();
    },
  };
}
