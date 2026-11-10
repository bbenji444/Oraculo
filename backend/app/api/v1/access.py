"""Endpoints ``/api/v1/access``: personas y llaves (solo superusuarios, ADR-0042).

La pantalla «Accesos» los usa para dar de alta personas, cambiarles el rol,
desactivarlas, y crear o revocar sus llaves. La llave completa sale **una
sola vez**, en la respuesta de ``POST /access/users/{id}/keys``; después
solo se ve su parte pública (``orc_live_a1b2c3d4…``).

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
from app.domain.access import KeyInfo, Role, UserAccount

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
    response_model=UserOut,
    status_code=status.HTTP_201_CREATED,
    summary="Dar de alta a una persona",
    responses=error_responses(409, 422),
)
async def create_user(body: UserIn, request: Request, admin: Admin, user: SuperUser) -> UserOut:
    """Crea a la persona sin llave; después se le crea una con ``POST …/keys``."""
    created = await admin.create_user(
        user,
        client_ip(request),
        username=body.username,
        display_name=body.display_name,
        email=body.email,
        role=body.role,
    )
    return UserOut.of(created)


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
