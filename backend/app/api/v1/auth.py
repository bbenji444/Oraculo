"""Endpoints ``/api/v1/auth``: entrar en pasos, salir, quién soy (ADR-0042 y 0043).

Entrar es igual que en Oráculo: usuario y contraseña, y luego el código de 6
dígitos de Microsoft Authenticator. Cada paso devuelve un ``ticket`` (el
ingreso a medias) que se manda en el siguiente:

- ``POST /auth/login`` → usuario y contraseña;
- ``POST /auth/login/password`` → primer ingreso: cambiar la temporal;
- ``POST /auth/login/enroll`` → primer ingreso: el QR del Authenticator;
- ``POST /auth/login/enroll/confirm`` → primer ingreso: primer código;
- ``POST /auth/login/code`` → el código de cada día.

El último paso responde con la cookie ``monitor_sesion``: el **token interno**
que identifica a la persona. Además:

- ``GET /auth/me``: quién soy y qué pestañas puedo abrir;
- ``POST /auth/password``: cambiar mi contraseña;
- ``POST /auth/logout``: salir;
- ``POST /auth/introspect``: para otros módulos de Oráculo, de quién es un
  token (pide llave de sistema).

Todo va en el cuerpo, nunca en la URL (las URLs quedan en logs e historiales).

No hace: no revisa contraseñas ni códigos (``PasswordLogin``).
"""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Request, Response, status
from pydantic import BaseModel, Field

from app.api.auth import SESSION_COOKIE, CurrentUser, SuperUser, client_ip
from app.api.errors import ERROR_RESPONSES, error_responses
from app.application.use_cases.access import Authenticator, OpenedSession
from app.application.use_cases.login import LoginStep, PasswordLogin
from app.domain.access import AuthUser, Role
from app.domain.credentials import MAX_PASSWORD_CHARS, TOTP_DIGITS
from app.domain.errors import ConflictError

router = APIRouter(prefix="/auth", tags=["acceso"], responses=ERROR_RESPONSES)

# Secciones de la pantalla por rol (Benji, 10/11/2026). «Envíos» se suma a
# los usuarios normales en la etapa 3 (envíos por persona, ADR-0042); hoy sus
# rutas son solo del superusuario.
_USER_SECTIONS = ["explorar", "casos", "conceptos", "historial"]
_SUPERUSER_SECTIONS = [*_USER_SECTIONS, "envios", "estado", "accesos"]
# Topes de tamaño de lo que llega (un usuario mide 60; un ticket, 43).
_MAX_USERNAME = 60
_MAX_TICKET = 100
_MAX_CODE = 12


class LoginIn(BaseModel):
    """Paso 1: usuario y contraseña."""

    username: str = Field(min_length=1, max_length=_MAX_USERNAME, examples=["benji"])
    password: str = Field(min_length=1, max_length=MAX_PASSWORD_CHARS)


class StepOut(BaseModel):
    """Qué sigue en el ingreso."""

    ticket: str = Field(description="Mándalo en el siguiente paso; vence en 10 minutos.")
    next: Literal["code", "change_password", "enroll"] = Field(
        description="code: escribir el código; change_password: cambiar la temporal; "
        "enroll: dar de alta Microsoft Authenticator."
    )

    @classmethod
    def of(cls, step: LoginStep) -> "StepOut":
        """Desde el caso de uso."""
        return cls(ticket=step.ticket, next=step.next)


class TicketIn(BaseModel):
    """Solo el ticket."""

    ticket: str = Field(min_length=1, max_length=_MAX_TICKET)


class CodeIn(TicketIn):
    """El ticket y el código de 6 dígitos."""

    code: str = Field(min_length=TOTP_DIGITS, max_length=_MAX_CODE, examples=["123456"])


class NewPasswordIn(TicketIn):
    """El ticket y la contraseña nueva."""

    new_password: str = Field(min_length=1, max_length=MAX_PASSWORD_CHARS)


class EnrollmentOut(BaseModel):
    """Lo necesario para dar de alta Microsoft Authenticator."""

    qr_svg: str = Field(description="Código QR (SVG) para escanear con la app.")
    secret: str = Field(description="El mismo secreto, por si hay que teclearlo.")
    uri: str = Field(description="El otpauth:// que lleva el QR.")


class ChangePasswordIn(BaseModel):
    """Cambiar mi contraseña con la sesión abierta."""

    current_password: str = Field(min_length=1, max_length=MAX_PASSWORD_CHARS)
    new_password: str = Field(min_length=1, max_length=MAX_PASSWORD_CHARS)


class MeOut(BaseModel):
    """La persona que entró."""

    username: str = Field(examples=["benji"])
    display_name: str = Field(examples=["Benjamin"])
    role: Role
    sections: list[str] = Field(description="Pestañas que puede abrir.")
    auth_mode: str = Field(description="keys: con acceso; dev: sin acceso (solo desarrollo).")

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


class IntrospectIn(BaseModel):
    """Un token interno que otro módulo quiere identificar."""

    token: str = Field(min_length=1, max_length=_MAX_TICKET)


class IntrospectOut(BaseModel):
    """De quién es el token (``active`` falso si no sirve)."""

    active: bool
    username: str | None = None
    display_name: str | None = None
    role: Role | None = None


def get_authenticator(request: Request) -> Authenticator:
    """El autenticador armado al arrancar (solo en modo ``keys``).

    Raises:
        ConflictError: En modo ``dev`` (no se entra con contraseña).
    """
    authenticator: Authenticator | None = getattr(request.app.state, "authenticator", None)
    if authenticator is None:
        raise ConflictError("En modo de desarrollo no se entra con contraseña.")
    return authenticator


def get_password_login(request: Request) -> PasswordLogin:
    """El ingreso en pasos armado al arrancar (solo en modo ``keys``).

    Raises:
        ConflictError: En modo ``dev``.
    """
    login: PasswordLogin | None = getattr(request.app.state, "password_login", None)
    if login is None:
        raise ConflictError("En modo de desarrollo no se entra con contraseña.")
    return login


Auth = Annotated[Authenticator, Depends(get_authenticator)]
Login = Annotated[PasswordLogin, Depends(get_password_login)]


def _with_session(opened: OpenedSession, request: Request, response: Response) -> MeOut:
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


@router.post(
    "/login",
    response_model=StepOut,
    summary="Entrar: usuario y contraseña",
    responses=error_responses(401, 409, 429),
)
async def login(body: LoginIn, request: Request, response: Response, steps: Login) -> StepOut:
    """Revisa usuario y contraseña; responde qué sigue (normalmente, el código)."""
    response.headers["Cache-Control"] = "no-store"
    return StepOut.of(await steps.start(body.username, body.password, client_ip(request)))


@router.post(
    "/login/password",
    response_model=StepOut,
    summary="Primer ingreso: cambiar la contraseña temporal",
    responses=error_responses(401, 409, 422),
)
async def first_password(body: NewPasswordIn, request: Request, steps: Login) -> StepOut:
    """Al menos 12 caracteres, con letras y números, sin el usuario."""
    return StepOut.of(
        await steps.change_password(body.ticket, body.new_password, client_ip(request))
    )


@router.post(
    "/login/enroll",
    response_model=EnrollmentOut,
    summary="Primer ingreso: QR de Microsoft Authenticator",
    responses=error_responses(401, 409),
)
async def enroll(body: TicketIn, response: Response, steps: Login) -> EnrollmentOut:
    """Genera el QR. El secreto queda cifrado hasta confirmar con un código."""
    enrollment = await steps.start_enrollment(body.ticket)
    response.headers["Cache-Control"] = "no-store"
    return EnrollmentOut(qr_svg=enrollment.qr_svg, secret=enrollment.secret, uri=enrollment.uri)


@router.post(
    "/login/enroll/confirm",
    response_model=MeOut,
    summary="Primer ingreso: confirmar el Authenticator con un código",
    responses=error_responses(401, 409),
)
async def confirm_enroll(body: CodeIn, request: Request, response: Response, steps: Login) -> MeOut:
    """El primer código confirma que el celular quedó bien y abre la sesión."""
    opened = await steps.confirm_enrollment(body.ticket, body.code, client_ip(request))
    return _with_session(opened, request, response)


@router.post(
    "/login/code",
    response_model=MeOut,
    summary="Entrar: código de 6 dígitos",
    responses=error_responses(401, 409, 429),
)
async def login_code(body: CodeIn, request: Request, response: Response, steps: Login) -> MeOut:
    """El código de Microsoft Authenticator abre la sesión (hasta 30 días o «Salir»)."""
    opened = await steps.verify_code(body.ticket, body.code, client_ip(request))
    return _with_session(opened, request, response)


@router.post(
    "/password",
    response_model=MeOut,
    summary="Cambiar mi contraseña",
    responses=error_responses(409, 422),
)
async def change_password(
    body: ChangePasswordIn,
    request: Request,
    response: Response,
    user: CurrentUser,
    steps: Login,
) -> MeOut:
    """Cierra las demás sesiones de la persona y deja abierta la de este navegador."""
    opened = await steps.change_own_password(
        user, body.current_password, body.new_password, client_ip(request)
    )
    return _with_session(opened, request, response)


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


@router.post(
    "/introspect",
    response_model=IntrospectOut,
    summary="De quién es un token interno (para otros módulos)",
    responses=error_responses(403, 409),
)
async def introspect(body: IntrospectIn, auth: Auth, _: SuperUser) -> IntrospectOut:
    """Otro módulo manda el token que recibió y sabe quién es, sin pedir contraseña.

    Quien pregunta debe identificarse con una llave de sistema de un
    superusuario (``Authorization: Bearer orc_live_…``).
    """
    user = await auth.introspect(body.token)
    if user is None:
        return IntrospectOut(active=False)
    return IntrospectOut(
        active=True, username=user.username, display_name=user.display_name, role=user.role
    )
