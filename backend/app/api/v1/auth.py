"""Endpoints ``/api/v1/auth``: entrar con llave, salir y quién soy (ADR-0042).

- ``POST /auth/login`` recibe la llave en el cuerpo (nunca en la URL: las
  URLs quedan en logs e historiales) y responde con la cookie de sesión.
- ``POST /auth/logout`` cierra la sesión.
- ``GET /auth/me`` dice quién es la persona y qué secciones puede abrir.

No hace: no revisa llaves por sí mismo (``Authenticator``).
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status
from pydantic import BaseModel, Field

from app.api.auth import SESSION_COOKIE, CurrentUser, client_ip
from app.api.errors import ERROR_RESPONSES, error_responses
from app.application.use_cases.access import Authenticator
from app.domain.access import AuthUser, Role
from app.domain.errors import ConflictError

router = APIRouter(prefix="/auth", tags=["acceso"], responses=ERROR_RESPONSES)

# Secciones de la pantalla por rol (Benji, 10/11/2026). «Envíos» se suma a
# los usuarios normales en la etapa 3 (envíos por persona, ADR-0042); hoy sus
# rutas son solo del superusuario.
_USER_SECTIONS = ["explorar", "casos", "conceptos", "historial"]
_SUPERUSER_SECTIONS = [*_USER_SECTIONS, "envios", "estado", "accesos"]
# El cuerpo de login es solo la llave: con 200 caracteres sobra (mide 58).
_MAX_KEY_CHARS = 200


class LoginIn(BaseModel):
    """La llave que pega la persona."""

    key: str = Field(min_length=1, max_length=_MAX_KEY_CHARS, examples=["orc_live_…"])


class MeOut(BaseModel):
    """La persona que entró."""

    username: str = Field(examples=["benji"])
    display_name: str = Field(examples=["Benjamin"])
    role: Role
    sections: list[str] = Field(description="Pestañas que puede abrir.")
    auth_mode: str = Field(description="keys: con llave; dev: sin llave (solo desarrollo).")

    @classmethod
    def of(cls, user: AuthUser, auth_mode: str) -> "MeOut":
        """Arma la respuesta a partir de la persona."""
        return cls(
            username=user.username,
            display_name=user.display_name,
            role=user.role,
            sections=_SUPERUSER_SECTIONS if user.is_superuser else _USER_SECTIONS,
            auth_mode=auth_mode,
        )


def get_authenticator(request: Request) -> Authenticator:
    """El autenticador armado al arrancar (solo en modo ``keys``).

    Raises:
        ConflictError: En modo ``dev`` (no hay llaves que revisar).
    """
    authenticator: Authenticator | None = getattr(request.app.state, "authenticator", None)
    if authenticator is None:
        raise ConflictError("En modo de desarrollo no se entra con llave.")
    return authenticator


Auth = Annotated[Authenticator, Depends(get_authenticator)]


@router.post(
    "/login",
    response_model=MeOut,
    summary="Entrar con una llave de acceso",
    responses=error_responses(401, 409, 429),
)
async def login(body: LoginIn, request: Request, response: Response, auth: Auth) -> MeOut:
    """Revisa la llave y abre una sesión con cookie ``HttpOnly`` de hasta 8 h."""
    opened = await auth.login(body.key, client_ip(request))
    response.set_cookie(
        SESSION_COOKIE,
        opened.token,
        max_age=opened.max_seconds,
        httponly=True,
        secure=request.app.state.auth_cookie_secure,
        samesite="strict",
        path="/api",
    )
    response.headers["Cache-Control"] = "no-store"
    return MeOut.of(opened.user, request.app.state.auth_mode)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, summary="Salir (cerrar la sesión)")
async def logout(request: Request) -> Response:
    """Cierra la sesión de esta cookie. Si no había, no pasa nada."""
    token = request.cookies.get(SESSION_COOKIE)
    authenticator: Authenticator | None = getattr(request.app.state, "authenticator", None)
    if token and authenticator is not None:
        await authenticator.logout(token)
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    response.delete_cookie(SESSION_COOKIE, path="/api")
    return response


@router.get("/me", response_model=MeOut, summary="Quién soy y qué puedo abrir")
async def me(user: CurrentUser, request: Request) -> MeOut:
    """La persona de la sesión (o de la llave Bearer) y sus secciones."""
    return MeOut.of(user, request.app.state.auth_mode)
