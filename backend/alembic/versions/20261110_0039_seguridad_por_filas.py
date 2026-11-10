"""Seguridad por filas (RLS): cada persona ve solo sus búsquedas (ADR-0042).

Benji pidió (10/11/2026) que cada usuario tenga su propio historial y que la
separación la haga la base, no solo la pantalla. Con RLS, aunque una ruta de
la API olvide filtrar, PostgreSQL no entrega filas ajenas.

Cómo decide la base (variables que pone la API en cada transacción, ver
``app/adapters/persistence/access_scope.py``):

- ``app_privileged()``: verdadero para ``superuser`` y ``system``, y cuando
  no hay variable (worker, comandos, Alembic: corren en el servidor);
- ``app_username()``: la persona de la petición.

Políticas:

- ``searches``: las propias (``user_id``) o todas si es privilegiado;
- ``search_results``, ``search_concepts``, ``processing_errors`` y
  ``reports``: las de una búsqueda que la persona puede ver;
- ``users`` y ``access_keys``: solo privilegiados (entrar con llave revisa
  como ``system``; las personas normales no listan a nadie).

``FORCE`` hace que las políticas valgan también para el dueño de las tablas
(el rol ``monitor`` con el que se conecta todo). Un superusuario de
PostgreSQL las saltaría: el rol ``monitor`` no lo es (revisado en la PC y en
el servidor general).

Revisión: 0039
Anterior: 0038
Fecha: 2026-11-10
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0039"
down_revision: str | None = "0038"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_FUNCTIONS = """
CREATE FUNCTION app_privileged() RETURNS boolean
LANGUAGE sql STABLE AS $$
    SELECT coalesce(current_setting('app.role', true), '') IN ('', 'system', 'superuser')
$$;
CREATE FUNCTION app_username() RETURNS text
LANGUAGE sql STABLE AS $$
    SELECT coalesce(current_setting('app.username', true), '')
$$;
"""

# Tablas hijas de una búsqueda: se ven si se ve la búsqueda (la subconsulta a
# searches pasa por su propia política).
_SEARCH_CHILDREN = ("search_results", "search_concepts", "processing_errors", "reports")
_ADMIN_ONLY = ("users", "access_keys")


def _enable(table: str) -> None:
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")


def upgrade() -> None:
    """Crea las funciones y las políticas, y enciende RLS."""
    op.execute(_FUNCTIONS)
    _enable("searches")
    op.execute(
        "CREATE POLICY searches_owner ON searches "
        "USING (app_privileged() OR user_id = app_username()) "
        "WITH CHECK (app_privileged() OR user_id = app_username())"
    )
    for table in _SEARCH_CHILDREN:
        _enable(table)
        # Nombres de tabla fijos de esta migración, no datos de nadie.
        cond = (
            f"app_privileged() OR EXISTS (SELECT 1 FROM searches s WHERE s.id = {table}.search_id)"  # noqa: S608 — tablas fijas
        )
        op.execute(f"CREATE POLICY {table}_by_search ON {table} USING ({cond}) WITH CHECK ({cond})")
    for table in _ADMIN_ONLY:
        _enable(table)
        op.execute(
            f"CREATE POLICY {table}_admin ON {table} "
            "USING (app_privileged()) WITH CHECK (app_privileged())"
        )


def downgrade() -> None:
    """Apaga RLS y borra políticas y funciones."""
    for table in _ADMIN_ONLY:
        op.execute(f"DROP POLICY {table}_admin ON {table}")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
    for table in _SEARCH_CHILDREN:
        op.execute(f"DROP POLICY {table}_by_search ON {table}")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
    op.execute("DROP POLICY searches_owner ON searches")
    op.execute("ALTER TABLE searches NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE searches DISABLE ROW LEVEL SECURITY")
    op.execute("DROP FUNCTION app_username()")
    op.execute("DROP FUNCTION app_privileged()")
