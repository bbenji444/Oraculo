"""Entorno de ejecución de Alembic.

Toma la URL de la base de ``app.core.config`` (variables de entorno). Si la
variable ``ALEMBIC_TARGET=test`` está definida, migra la base de pruebas en
lugar de la de desarrollo; así las pruebas de integración usan el mismo
esquema que la aplicación.

No hace: todavía no compara modelos (``target_metadata``): en F0 no hay
tablas. Se conectará a los modelos de ``adapters/persistence`` en F1.
"""

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

from app.core.config import get_settings

config = context.config
target_metadata = None

# Usa la sección [loggers] de alembic.ini para que `make migrate` diga qué
# migraciones aplicó. disable_existing_loggers=False respeta los logs JSON
# de la aplicación cuando Alembic corre dentro de las pruebas.
if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)


def _database_url() -> str:
    """URL de la base a migrar, con contraseña, para el engine de Alembic."""
    use_test_db = os.environ.get("ALEMBIC_TARGET") == "test"
    url = get_settings().database_url(test=use_test_db)
    return url.render_as_string(hide_password=False)


def run_migrations_offline() -> None:
    """Genera el SQL de las migraciones sin conectarse (``alembic upgrade --sql``)."""
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Aplica las migraciones conectándose a la base."""
    # NullPool: Alembic hace una sola conexión y termina; no necesita pool.
    engine = create_engine(_database_url(), poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
