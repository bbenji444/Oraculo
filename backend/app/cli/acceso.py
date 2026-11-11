"""Comando ``make acceso``: contraseña temporal desde la consola (ADR-0043).

Sirve para el **primer** superusuario (antes de que alguien pueda entrar a
«Accesos») y para recuperar el acceso si se perdió la contraseña o el
celular. La persona entra con la temporal, la cambia y escanea el QR de
Microsoft Authenticator.

La contraseña se muestra **una sola vez** en la terminal (o se escribe en un
archivo que solo puede leer el dueño, con ``--archivo``) y nunca pasa por los
logs. En la base queda solo su huella.

Uso:
    ``make acceso ARGS="--usuario benji"``: contraseña temporal nueva.
    ``make acceso ARGS="--usuario benji --reiniciar-codigo"``: además borra su
    Authenticator (cambió de celular) para que escanee un QR nuevo.
    ``make acceso ARGS="--usuario benji --archivo ~/acceso_benji.txt"``.

No hace: no crea personas (eso es en «Accesos»; ``benji`` ya existe).
"""

import argparse
import asyncio
import logging
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.ext.asyncio import create_async_engine

from app.adapters.persistence.access_repository import PostgresAccessStore
from app.application.use_cases.access import AccessAdmin
from app.cli.crear_llave import CONSOLE, NoSessions, write_private
from app.core.config import Settings, get_settings
from app.geodata.consola import configure_cli_logging, heading

logger = logging.getLogger(__name__)

# El secreto del servidor no se usa aquí (no se crean llaves), pero
# AccessAdmin lo pide; uno vacío deja claro que no participa.
_NO_PEPPER = b""


def parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    """Lee las opciones del comando.

    Args:
        argv: Argumentos (por defecto, los de la línea de comandos).

    Returns:
        Las opciones.
    """
    parser = argparse.ArgumentParser(description="Contraseña temporal para entrar al monitor.")
    parser.add_argument("--usuario", required=True, help="usuario (por ejemplo benji)")
    parser.add_argument(
        "--reiniciar-codigo",
        action="store_true",
        help="también borrar su Authenticator (escaneará un QR nuevo)",
    )
    parser.add_argument("--archivo", type=Path, help="escribir la contraseña aquí (permisos 600)")
    return parser.parse_args(argv)


async def run(args: argparse.Namespace, settings: Settings) -> int:
    """Flujo completo del comando.

    Args:
        args: Opciones.
        settings: Configuración.

    Returns:
        0 bien; 1 si la persona no existe.
    """
    engine = create_async_engine(settings.database_url())
    try:
        admin = AccessAdmin(
            PostgresAccessStore(engine), NoSessions(), _NO_PEPPER, lambda: datetime.now(UTC)
        )
        users = {u.username: u for u in await admin.list_users(CONSOLE)}
        user = users.get(args.usuario.strip().lower())
        if user is None:
            logger.error(f"No existe la persona «{args.usuario}». Existen: {', '.join(users)}")
            return 1
        temporary = await admin.reset_password(CONSOLE, None, user.user_id)
        if args.reiniciar_codigo:
            await admin.reset_totp(CONSOLE, None, user.user_id)
            logger.info("Se borró su Authenticator: al entrar escaneará un QR nuevo.")
        if args.archivo:
            write_private(args.archivo, temporary)
            logger.info(f"Contraseña temporal de {user.username} escrita en {args.archivo}")
            logger.info("Ábrela tú, úsala para entrar y borra el archivo (rm).")
        else:
            heading(logger, f"Contraseña temporal de {user.username} (se muestra una sola vez)")
            # A la terminal y no al log: nunca debe quedar en un archivo de logs.
            sys.stdout.write(f"\n    {temporary}\n\n")
            sys.stdout.flush()
        logger.info("Al entrar se pide cambiarla por una propia.")
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
