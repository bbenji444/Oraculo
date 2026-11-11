"""Comando ``make crear-llave``: crea una llave de sistema desde la consola (ADR-0042).

Las personas entran con usuario, contraseña y código (ADR-0043, ``make
acceso``); las llaves son para **sistemas** que se conectan al monitor con
``Authorization: Bearer``. Normalmente se crean en «Accesos»; este comando
sirve cuando todavía nadie puede entrar a la pantalla.

La llave completa se muestra **una sola vez** en la terminal (o se escribe en
un archivo que solo puede leer el dueño, con ``--archivo``) y nunca pasa por
los logs. En la base queda solo su huella.

Uso:
    ``make crear-llave ARGS="--usuario benji --etiqueta 'PC oficina' --dias 365"``
    ``make crear-llave ARGS="--usuario benji --archivo ~/llave_benji.txt"``
    ``make crear-llave ARGS=--listar``: personas y llaves, sin secretos.

No hace: no crea personas (eso es en «Accesos»; ``benji`` ya existe por la
migración 0038).
"""

import argparse
import asyncio
import logging
import os
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.ext.asyncio import create_async_engine

from app.adapters.persistence.access_repository import PostgresAccessStore
from app.application.use_cases.access import AccessAdmin
from app.core.config import Settings, get_settings
from app.domain.access import AuthUser, Role
from app.domain.errors import DomainError
from app.geodata.consola import configure_cli_logging, heading

logger = logging.getLogger(__name__)

# Quién firma en la bitácora: la consola del servidor (solo quien entra por SSH).
CONSOLE = AuthUser(0, "consola", "Consola del servidor", Role.SUPERUSER)
# Solo el dueño del archivo puede leerlo (rw-------).
_PRIVATE_FILE_MODE = 0o600


class NoSessions:
    """``SessionStorePort`` vacío: desde la consola no hay sesiones que cerrar.

    Las sesiones viven en el Redis de la API; si hiciera falta sacar a
    alguien al instante, se revoca desde «Accesos». De todos modos, cada
    sesión vuelve a revisar la base cada 5 minutos.
    """

    async def create(self, *_: object) -> str:
        """No se usa desde la consola."""
        raise NotImplementedError

    async def get(self, *_: object) -> None:
        """No hay sesiones en la consola."""
        return

    async def save(self, *_: object) -> None:
        """No hay sesiones en la consola."""
        return

    async def delete(self, *_: object) -> None:
        """No hay sesiones en la consola."""
        return

    async def delete_for_user(self, *_: object) -> int:
        """No hay sesiones en la consola: no cierra ninguna."""
        return 0


def parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    """Lee las opciones del comando.

    Args:
        argv: Argumentos (por defecto, los de la línea de comandos).

    Returns:
        Las opciones.
    """
    parser = argparse.ArgumentParser(description="Crea una llave de acceso del monitor.")
    parser.add_argument("--usuario", help="usuario dueño de la llave (por ejemplo benji)")
    parser.add_argument("--etiqueta", default="Creada en la consola", help="para qué es")
    parser.add_argument("--dias", type=int, default=None, help="vigencia 1-365; sin valor no vence")
    parser.add_argument("--archivo", type=Path, help="escribir la llave aquí (permisos 600)")
    parser.add_argument("--listar", action="store_true", help="solo listar personas y llaves")
    return parser.parse_args(argv)


def write_private(path: Path, content: str) -> None:
    """Escribe un secreto en un archivo nuevo que solo puede leer su dueño (600).

    Raises:
        FileExistsError: Si el archivo ya existe (no se pisa otro secreto).
    """
    path = path.expanduser()
    # O_EXCL: no pisa un archivo que ya exista (podría ser otra llave).
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, _PRIVATE_FILE_MODE)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(content + "\n")


async def _list(admin: AccessAdmin) -> None:
    heading(logger, "Personas y llaves (sin secretos)")
    for user in await admin.list_users(CONSOLE):
        state = "activa" if user.is_active else "DESACTIVADA"
        logger.info(f"{user.username} ({user.role.value}, {state}): {user.active_keys} vigentes")
        for key in await admin.user_keys(CONSOLE, user.user_id):
            status = "revocada" if key.revoked_at else "vigente"
            logger.info(f"   {key.masked} {status} · {key.label} · vence {key.expires_at}")


async def run(args: argparse.Namespace, settings: Settings) -> int:
    """Flujo completo del comando.

    Args:
        args: Opciones.
        settings: Configuración.

    Returns:
        0 bien; 1 si falta la pimienta, la persona no existe o una regla lo impide.
    """
    if settings.auth_key_pepper is None:
        logger.error("Falta AUTH_KEY_PEPPER en el .env: sin ella las llaves no se pueden revisar.")
        return 1
    engine = create_async_engine(settings.database_url())
    try:
        store = PostgresAccessStore(engine)
        admin = AccessAdmin(
            store,
            NoSessions(),
            settings.auth_key_pepper.get_secret_value().encode(),
            lambda: datetime.now(UTC),
        )
        if args.listar:
            await _list(admin)
            return 0
        users = {u.username: u for u in await admin.list_users(CONSOLE)}
        user = users.get((args.usuario or "").strip().lower())
        if user is None:
            logger.error(f"No existe la persona «{args.usuario}». Existen: {', '.join(users)}")
            return 1
        try:
            issued = await admin.issue_key(CONSOLE, None, user.user_id, args.etiqueta, args.dias)
        except DomainError as error:
            logger.error(error.message)
            return 1
        if args.archivo:
            write_private(args.archivo, issued.key.full)
            logger.info(f"Llave {issued.key.masked} de {user.username} escrita en {args.archivo}")
            logger.info("Ábrela tú, cópiala y borra el archivo (rm).")
        else:
            heading(logger, f"Llave de {user.username} (cópiala ahora: no se vuelve a mostrar)")
            # A la terminal y no al log: la llave nunca debe quedar en un archivo de logs.
            sys.stdout.write(f"\n    {issued.key.full}\n\n")
            sys.stdout.flush()
        return 0
    finally:
        await engine.dispose()


def main(argv: Sequence[str] | None = None) -> None:
    """Punto de entrada de la línea de comandos.

    Args:
        argv: Argumentos (por defecto, los de la línea de comandos).
    """
    args = parse_args(argv)
    configure_cli_logging()
    raise SystemExit(asyncio.run(run(args, get_settings())))


if __name__ == "__main__":
    main()
