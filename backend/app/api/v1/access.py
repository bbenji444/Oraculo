"""Endpoints ``/api/v1/access``: personas y llaves (solo superusuarios).

La pantalla «Accesos» los usa para (ADR-0042 y ADR-0043):

- dar de alta personas: la respuesta trae su **contraseña temporal**, que se
  muestra una sola vez y la persona cambia al primer ingreso;
- cambiarles el rol, desactivarlas o borrarlas (borrado lógico);
- restablecer su contraseña (la olvidó) o su Microsoft Authenticator
  (cambió de celular);
- crear o revocar llaves de sistema. La llave completa sale **una sola
  vez**; después solo se ve su parte pública (``orc_live_a1b2c3d4…``);
- ver, copiar o regenerar la **llave de API** de cada persona, para
  conectarla con el resto de Oráculo (ADR-0047). Esa sí se guarda cifrada y
  se puede volver a ver; cada vista queda en la bitácora;
- prender o apagar el código de 6 dígitos al entrar (``/access/settings``).

No hace: no aplica las reglas (``AccessAdmin``).
"""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Request, Response, status
from pydantic import BaseModel, Field

from app.api.auth import SuperUser, client_ip
from app.api.errors import ERROR_RESPONSES, error_responses
from app.application.ports.access import UserChanges
from app.application.use_cases.access import AccessAdmin
from app.domain.access import KEY_PREFIX, KeyInfo, Role, UserAccount

router = APIRouter(prefix="/access", tags=["acceso"], responses=ERROR_RESPONSES)


class UserOut(BaseModel):
    """Una persona."""

    id: int
    username: str
    display_name: str
    email: str | None
    role: Role
    is_active: bool
    created_at: datetime
    last_seen_at: datetime | None
    active_keys: int = Field(description="Llaves vigentes (sin revocar ni vencer).")
    has_password: bool = Field(description="Si ya tiene contraseña.")
    must_change_password: bool = Field(description="Si su contraseña es temporal.")
    totp_enrolled: bool = Field(description="Si ya dio de alta Microsoft Authenticator.")
    locked_until: datetime | None = Field(description="Bloqueada por intentos hasta esta hora.")
    api_key: str | None = Field(
        default=None,
        description="Su llave de API, enmascarada (orc_live_a1b2c3d4…); null si no tiene.",
    )

    @classmethod
    def of(cls, user: UserAccount) -> "UserOut":
        """Desde el dominio."""
        return cls(
            id=user.user_id,
            username=user.username,
            display_name=user.display_name,
            email=user.email,
            role=user.role,
            is_active=user.is_active,
            created_at=user.created_at,
            last_seen_at=user.last_seen_at,
            active_keys=user.active_keys,
            has_password=user.has_password,
            must_change_password=user.must_change_password,
            totp_enrolled=user.totp_enrolled,
            locked_until=user.locked_until,
            api_key=f"{KEY_PREFIX}{user.api_key_prefix}…" if user.api_key_prefix else None,
        )


class UserListOut(BaseModel):
    """Todas las personas."""

    items: list[UserOut]


class UserIn(BaseModel):
    """Alta de una persona."""

    username: str = Field(min_length=1, max_length=60, examples=["ana.lopez"])
    display_name: str = Field(min_length=1, max_length=120, examples=["Ana López"])
    email: str | None = Field(default=None, max_length=254)
    role: Role = Role.USER


class CreatedUserOut(BaseModel):
    """Persona recién creada con su contraseña temporal (solo esta vez)."""

    user: UserOut
    temporary_password: str = Field(
        description="Dásela a la persona; la cambia al primer ingreso. No se vuelve a mostrar."
    )


class TemporaryPasswordOut(BaseModel):
    """Contraseña temporal nueva (solo esta vez)."""

    temporary_password: str


class UserPatch(BaseModel):
    """Cambios a una persona; lo que no venga no se toca."""

    display_name: str | None = Field(default=None, max_length=120)
    email: str | None = Field(default=None, max_length=254, description='"" borra el correo.')
    role: Role | None = None
    is_active: bool | None = None


class KeyOut(BaseModel):
    """Una llave, sin su secreto."""

    id: int
    user_id: int
    masked: str = Field(examples=["orc_live_a1b2c3d4…"])
    label: str
    created_by: str
    created_at: datetime
    expires_at: datetime | None
    revoked_at: datetime | None
    last_used_at: datetime | None
    last_used_ip: str | None

    @classmethod
    def of(cls, key: KeyInfo) -> "KeyOut":
        """Desde el dominio."""
        return cls(
            id=key.key_id,
            user_id=key.user_id,
            masked=key.masked,
            label=key.label,
            created_by=key.created_by,
            created_at=key.created_at,
            expires_at=key.expires_at,
            revoked_at=key.revoked_at,
            last_used_at=key.last_used_at,
            last_used_ip=key.last_used_ip,
        )


class KeyListOut(BaseModel):
    """Las llaves de una persona."""

    items: list[KeyOut]


class KeyIn(BaseModel):
    """Una llave nueva."""

    label: str = Field(default="", max_length=80, examples=["Laptop de la oficina"])
    days: int | None = Field(
        default=90, ge=1, le=365, description="Días de vigencia; null = no vence."
    )


class AuthSettingsOut(BaseModel):
    """Cómo se entra al monitor."""

    totp_required: bool = Field(
        description="Si al entrar se pide el código de Microsoft Authenticator."
    )


class AuthSettingsIn(AuthSettingsOut):
    """Prender o apagar el código al entrar."""


class ApiKeyOut(BaseModel):
    """La llave de API de una persona, completa (ADR-0047)."""

    key: str = Field(description="La llave completa (Authorization: Bearer <key>).")
    info: KeyOut


class IssuedKeyOut(BaseModel):
    """La llave recién creada: ``key`` solo se muestra esta vez."""

    key: str = Field(description="La llave completa. Cópiala ahora: no se vuelve a mostrar.")
    info: KeyOut


def get_access_admin(request: Request) -> AccessAdmin:
    """La administración armada al arrancar (las pruebas la reemplazan)."""
    admin: AccessAdmin = request.app.state.access_admin
    return admin


Admin = Annotated[AccessAdmin, Depends(get_access_admin)]
UserId = Annotated[int, Path(description="Id de la persona.")]


@router.get("/users", response_model=UserListOut, summary="Personas con acceso")
async def list_users(admin: Admin, user: SuperUser) -> UserListOut:
    """Todas las personas: activas primero, con cuántas llaves vigentes tiene cada una."""
    return UserListOut(items=[UserOut.of(u) for u in await admin.list_users(user)])


@router.post(
    "/users",
    response_model=CreatedUserOut,
    status_code=status.HTTP_201_CREATED,
    summary="Dar de alta a una persona",
    responses=error_responses(409, 422),
)
async def create_user(
    body: UserIn, request: Request, response: Response, admin: Admin, user: SuperUser
) -> CreatedUserOut:
    """Crea a la persona con contraseña temporal (sale solo en esta respuesta)."""
    created = await admin.create_user(
        user,
        client_ip(request),
        username=body.username,
        display_name=body.display_name,
        email=body.email,
        role=body.role,
    )
    response.headers["Cache-Control"] = "no-store"
    return CreatedUserOut(
        user=UserOut.of(created.account), temporary_password=created.temporary_password
    )


@router.delete(
    "/users/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Borrar a una persona",
    responses=error_responses(404, 409),
)
async def delete_user(request: Request, admin: Admin, user: SuperUser, user_id: UserId) -> Response:
    """Desaparece de la lista y ya no puede entrar; sus búsquedas y la bitácora se quedan."""
    await admin.delete_user(user, client_ip(request), user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/users/{user_id}/reset-password",
    response_model=TemporaryPasswordOut,
    summary="Restablecer la contraseña (la olvidó)",
    responses=error_responses(404),
)
async def reset_password(
    request: Request, response: Response, admin: Admin, user: SuperUser, user_id: UserId
) -> TemporaryPasswordOut:
    """Contraseña temporal nueva; cierra sus sesiones. Su Authenticator no cambia."""
    temporary = await admin.reset_password(user, client_ip(request), user_id)
    response.headers["Cache-Control"] = "no-store"
    return TemporaryPasswordOut(temporary_password=temporary)


@router.post(
    "/users/{user_id}/reset-totp",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Reiniciar su Microsoft Authenticator (cambió de celular)",
    responses=error_responses(404),
)
async def reset_totp(request: Request, admin: Admin, user: SuperUser, user_id: UserId) -> Response:
    """Borra su código; al volver a entrar escanea un QR nuevo. Cierra sus sesiones."""
    await admin.reset_totp(user, client_ip(request), user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.patch(
    "/users/{user_id}",
    response_model=UserOut,
    summary="Cambiar nombre, correo, rol o desactivar",
    responses=error_responses(404, 409, 422),
)
async def update_user(
    body: UserPatch, request: Request, admin: Admin, user: SuperUser, user_id: UserId
) -> UserOut:
    """Desactivar o cambiar el rol cierra sus sesiones abiertas."""
    changes = UserChanges(
        display_name=body.display_name,
        email=body.email,
        role=body.role,
        is_active=body.is_active,
    )
    return UserOut.of(await admin.update_user(user, client_ip(request), user_id, changes))


@router.get(
    "/users/{user_id}/keys",
    response_model=KeyListOut,
    summary="Llaves de una persona",
    responses=error_responses(404),
)
async def list_keys(admin: Admin, user: SuperUser, user_id: UserId) -> KeyListOut:
    """Sus llaves, la más nueva primero, sin secretos."""
    return KeyListOut(items=[KeyOut.of(k) for k in await admin.user_keys(user, user_id)])


@router.post(
    "/users/{user_id}/keys",
    response_model=IssuedKeyOut,
    status_code=status.HTTP_201_CREATED,
    summary="Crear una llave",
    responses=error_responses(404, 409, 422),
)
async def issue_key(  # noqa: PLR0913 — cuerpo, petición, respuesta y dependencias, por nombre (*)
    body: KeyIn,
    *,
    request: Request,
    response: Response,
    admin: Admin,
    user: SuperUser,
    user_id: UserId,
) -> IssuedKeyOut:
    """La llave completa sale solo en esta respuesta: cópiala y entrégala a la persona."""
    issued = await admin.issue_key(user, client_ip(request), user_id, body.label, body.days)
    response.headers["Cache-Control"] = "no-store"
    return IssuedKeyOut(key=issued.key.full, info=KeyOut.of(issued.info))


@router.delete(
    "/keys/{key_id}",
    response_model=KeyOut,
    summary="Revocar una llave",
    responses=error_responses(404, 409),
)
async def revoke_key(
    request: Request,
    admin: Admin,
    user: SuperUser,
    key_id: Annotated[int, Path(description="Id de la llave.")],
) -> KeyOut:
    """Deja de servir al instante y cierra las sesiones que entraron con ella."""
    return KeyOut.of(await admin.revoke_key(user, client_ip(request), key_id))


@router.get(
    "/settings",
    response_model=AuthSettingsOut,
    summary="Cómo se entra al monitor",
)
async def auth_settings(admin: Admin, user: SuperUser) -> AuthSettingsOut:
    """Si al entrar se pide el código de 6 dígitos."""
    return AuthSettingsOut(totp_required=await admin.totp_required(user))


@router.put(
    "/settings",
    response_model=AuthSettingsOut,
    summary="Prender o apagar el código al entrar",
)
async def save_auth_settings(
    body: AuthSettingsIn, request: Request, admin: Admin, user: SuperUser
) -> AuthSettingsOut:
    """Aplica desde el siguiente ingreso; las sesiones abiertas siguen."""
    required = await admin.set_totp_required(user, client_ip(request), body.totp_required)
    return AuthSettingsOut(totp_required=required)


@router.get(
    "/users/{user_id}/api-key",
    response_model=ApiKeyOut,
    summary="Ver la llave de API de una persona",
    responses=error_responses(404),
)
async def show_api_key(
    request: Request, response: Response, admin: Admin, user: SuperUser, user_id: UserId
) -> ApiKeyOut:
    """La llave completa, para copiarla; queda en la bitácora quién la vio."""
    shown = await admin.show_api_key(user, client_ip(request), user_id)
    response.headers["Cache-Control"] = "no-store"
    return ApiKeyOut(key=shown.key.full, info=KeyOut.of(shown.info))


@router.post(
    "/users/{user_id}/api-key",
    response_model=ApiKeyOut,
    status_code=status.HTTP_201_CREATED,
    summary="Generar la llave de API de una persona",
    responses=error_responses(404, 409),
)
async def new_api_key(
    request: Request, response: Response, admin: Admin, user: SuperUser, user_id: UserId
) -> ApiKeyOut:
    """Crea una llave nueva; la anterior deja de servir al instante."""
    issued = await admin.new_api_key(user, client_ip(request), user_id)
    response.headers["Cache-Control"] = "no-store"
    return ApiKeyOut(key=issued.key.full, info=KeyOut.of(issued.info))
