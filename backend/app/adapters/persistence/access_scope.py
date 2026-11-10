"""Quién consulta la base: el «contexto» que usa la seguridad por filas (RLS).

PostgreSQL filtra solo las filas de ``searches``, ``search_results``,
``reports``, ``users`` y ``access_keys`` según dos variables de la
transacción (migración 0039, ADR-0042):

- ``app.role``: ``superuser``, ``user``, ``system`` o ``anonymous``;
- ``app.username``: el identificador de la persona («benji»).

Este módulo las llena:

- **la API** usa :func:`create_api_engine`: cada conexión nace como
  ``anonymous`` (no ve nada protegido) y, al empezar cada transacción, se
  ponen los valores de la persona de la petición (:func:`as_user`) o de una
  tarea interna (:func:`as_system`, por ejemplo revisar una llave al entrar);
- **el worker, los comandos y Alembic** no ponen nada: sin variables, las
  políticas los tratan como el sistema (corren en el servidor, no por HTTP).

No hace: no decide quién es la persona (eso es de ``app.api.auth``) ni
define las políticas (migración 0039).
"""

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass

from sqlalchemy import URL, event
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.domain.access import AuthUser

# Valores de app.role que entienden las políticas de la migración 0039.
ROLE_ANONYMOUS = "anonymous"
ROLE_SYSTEM = "system"


@dataclass(frozen=True, slots=True)
class DbScope:
    """Lo que se le dice a PostgreSQL en cada transacción.

    Attributes:
        role: Valor de ``app.role``.
        username: Valor de ``app.username`` (vacío si no hay persona).
    """

    role: str
    username: str = ""


_ANONYMOUS = DbScope(ROLE_ANONYMOUS)
_SYSTEM = DbScope(ROLE_SYSTEM)
# contextvars: cada petición (tarea de asyncio) ve el suyo, aunque corran a
# la vez; SQLAlchemy lo hereda en el hilo verde donde ejecuta.
_scope: ContextVar[DbScope] = ContextVar("db_scope", default=_ANONYMOUS)


def current_scope() -> DbScope:
    """El contexto de la tarea actual (``anonymous`` si nadie lo puso)."""
    return _scope.get()


def set_user_scope(user: AuthUser) -> None:
    """Pone a la persona como contexto del resto de la petición actual.

    Lo usa el candado de la API: la petición corre en su propia tarea, así
    que el valor no se filtra a otras peticiones.
    """
    _scope.set(DbScope(user.role.value, user.username))


@contextmanager
def as_user(user: AuthUser) -> Iterator[None]:
    """Consultas dentro del bloque, a nombre de la persona."""
    token = _scope.set(DbScope(user.role.value, user.username))
    try:
        yield
    finally:
        _scope.reset(token)


@contextmanager
def as_system() -> Iterator[None]:
    """Consultas dentro del bloque, como el sistema (ve todo).

    Solo para lo que la API necesita antes de saber quién es la persona:
    revisar una llave al entrar o una sesión.
    """
    token = _scope.set(_SYSTEM)
    try:
        yield
    finally:
        _scope.reset(token)


def _apply_scope(conn: Connection) -> None:
    scope = _scope.get()
    # set_config(..., true) vale solo para esta transacción: al terminar, la
    # conexión vuelve a «anonymous» antes de que la use otra petición.
    conn.exec_driver_sql(
        "SELECT set_config('app.role', %(role)s, true), "
        "set_config('app.username', %(username)s, true)",
        {"role": scope.role, "username": scope.username},
    )


def create_api_engine(url: URL, **kwargs: object) -> AsyncEngine:
    """Engine de la API: cada transacción lleva el contexto de la petición.

    Args:
        url: URL de la base.
        **kwargs: Opciones de ``create_async_engine`` (``pool_pre_ping``…).

    Returns:
        El engine listo; sin contexto, sus consultas no ven filas protegidas.
    """
    # options=-c: el valor de la conexión cuando no hay transacción abierta,
    # para que nada quede con permisos de otra petición por descuido.
    engine = create_async_engine(
        url, connect_args={"options": f"-c app.role={ROLE_ANONYMOUS}"}, **kwargs
    )
    event.listen(engine.sync_engine, "begin", _apply_scope)
    return engine
