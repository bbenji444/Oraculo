"""El candado de la API: quién hace cada petición (ADR-0042).

Toda ruta bajo ``/api/v1`` pide una de estas dos cosas, salvo las públicas
(``/health``, ``/app-config``, los pasos de ``/auth/login…`` y
``/auth/logout``):

- **cookie de sesión** ``monitor_sesion``: el token interno que se abre al
  entrar con usuario, contraseña y código (ADR-0043). Es ``HttpOnly`` (el
  JavaScript no la puede leer), ``SameSite=Strict`` y, en peticiones que
  cambian algo, el encabezado ``Origin`` debe ser el mismo servidor (CSRF);
- **llave de sistema en** ``Authorization: Bearer orc_live_…`` (otros
  programas, como las APIs de OpenAI o Claude; ADR-0042).

Con ``AUTH_MODE=dev`` (la PC y las pruebas) no se pide nada: todo va a
nombre de ``DEV_USER`` como superusuario.

Al reconocer a la persona, la guarda en ``request.state.user`` y en el
contexto de la base (seguridad por filas, ``access_scope``).

No hace: no revisa llaves ni sesiones por sí mismo (eso es de
``Authenticator``) ni decide qué puede hacer cada rol en cada ruta (lo
piden las rutas con ``require_superuser_user``).
"""

import ipaddress
from collections.abc import Awaitable, Callable
from typing import Annotated
from urllib.parse import urlsplit

from fastapi import Depends, FastAPI, Request, Response, status

from app.adapters.persistence.access_scope import set_user_scope
from app.api.errors import error_response
from app.application.use_cases.access import Authenticator, require_superuser
from app.domain.access import AuthUser, Role
from app.domain.errors import (
    AuthenticationRequiredError,
    DomainError,
    ForbiddenError,
    TooManyAttemptsError,
)

API_PREFIX = "/api/v1"
SESSION_COOKIE = "monitor_sesion"
# Rutas que se abren sin llave: el diagnóstico (lo usan make status y la
# actualización automática), la configuración pública y entrar/salir.
PUBLIC_PATHS = frozenset(
    {
        f"{API_PREFIX}/health",
        f"{API_PREFIX}/app-config",
        f"{API_PREFIX}/auth/login",
        f"{API_PREFIX}/auth/login/password",
        f"{API_PREFIX}/auth/login/enroll",
        f"{API_PREFIX}/auth/login/enroll/confirm",
        f"{API_PREFIX}/auth/login/code",
        f"{API_PREFIX}/auth/logout",
    }
)
_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
_BEARER = "bearer "
_NEED_KEY = "Entra con tu usuario y contraseña."
_BAD_ORIGIN = "Petición rechazada: no viene de la pantalla del monitor."


def dev_user(username: str) -> AuthUser:
    """La persona fija del modo ``dev`` (superusuario, id 0)."""
    return AuthUser(0, username, username.capitalize(), Role.SUPERUSER)


def client_ip(request: Request) -> str | None:
    """IP de quien pide, o ``None`` si no es una IP válida.

    uvicorn ya la toma de ``X-Forwarded-For`` cuando viene de nginx. El
    cliente de pruebas dice ``testclient`` y ``audit_log.ip`` es ``inet``:
    guardar texto rompería la bitácora.
    """
    host = request.client.host if request.client else None
    if host is None:
        return None
    try:
        return str(ipaddress.ip_address(host))
    except ValueError:
        return None


def _same_origin(request: Request) -> bool:
    source = request.headers.get("origin") or request.headers.get("referer")
    if not source:
        return False
    return urlsplit(source).netloc == request.headers.get("host", "")


async def _identify(request: Request) -> AuthUser:
    authenticator: Authenticator = request.app.state.authenticator
    header = request.headers.get("authorization", "")
    if header.lower().startswith(_BEARER):
        return await authenticator.from_bearer(header[len(_BEARER) :].strip(), client_ip(request))
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise AuthenticationRequiredError(_NEED_KEY)
    if request.method not in _SAFE_METHODS and not _same_origin(request):
        raise ForbiddenError(_BAD_ORIGIN)
    return await authenticator.from_session(token)


def install_auth(app: FastAPI) -> None:
    """Pone el candado a todas las rutas de ``/api/v1`` (menos las públicas).

    Args:
        app: La aplicación; debe tener ``app.state.auth_mode`` y, en modo
            ``keys``, ``app.state.authenticator``.
    """

    @app.middleware("http")
    async def auth_guard(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        path = request.url.path
        if not path.startswith(f"{API_PREFIX}/") or path in PUBLIC_PATHS:
            return await call_next(request)
        if request.app.state.auth_mode == "dev":
            user: AuthUser = request.app.state.dev_auth_user
        else:
            try:
                user = await _identify(request)
            except (AuthenticationRequiredError, TooManyAttemptsError, ForbiddenError) as error:
                return _refusal(error)
        request.state.user = user
        # El resto de la petición corre en otra tarea que hereda este contexto.
        set_user_scope(user)
        response = await call_next(request)
        response.headers.setdefault("Cache-Control", "no-store")
        return response


def _refusal(error: DomainError) -> Response:
    status_code = status.HTTP_403_FORBIDDEN
    if isinstance(error, AuthenticationRequiredError):
        status_code = status.HTTP_401_UNAUTHORIZED
    elif isinstance(error, TooManyAttemptsError):
        status_code = status.HTTP_429_TOO_MANY_REQUESTS
    response = error_response(status_code, error.code, error.message, error.details)
    if status_code == status.HTTP_401_UNAUTHORIZED:
        # Que el navegador olvide una cookie vencida.
        response.delete_cookie(SESSION_COOKIE, path="/api")
    return response


def get_current_user(request: Request) -> AuthUser:
    """La persona de la petición (la puso el candado).

    Raises:
        AuthenticationRequiredError: Si la ruta no pasó por el candado.
    """
    user: AuthUser | None = getattr(request.state, "user", None)
    if user is None:
        raise AuthenticationRequiredError(_NEED_KEY)
    return user


def require_superuser_user(request: Request) -> AuthUser:
    """Dependencia de las rutas solo para superusuarios.

    Raises:
        ForbiddenError: Si es un usuario normal.
    """
    user = get_current_user(request)
    require_superuser(user)
    return user


def superuser_for_changes(request: Request) -> None:
    """Dependencia de routers donde todos leen pero solo el superusuario cambia.

    Etapa 1 (ADR-0042): conceptos y subdivisiones son compartidos; editarlos
    cambiaría lo que ven todos. En la etapa 2 cada persona tendrá los suyos.

    Raises:
        ForbiddenError: Si un usuario normal intenta crear, editar o borrar.
    """
    # «Probar concepto» es POST pero no cambia nada: lo pueden usar todos.
    if request.method not in _SAFE_METHODS and not request.url.path.endswith("/preview"):
        user = get_current_user(request)
        if not user.is_superuser:
            raise ForbiddenError(
                "Por ahora solo un superusuario puede cambiar conceptos y subdivisiones."
            )


CurrentUser = Annotated[AuthUser, Depends(get_current_user)]
SuperUser = Annotated[AuthUser, Depends(require_superuser_user)]
