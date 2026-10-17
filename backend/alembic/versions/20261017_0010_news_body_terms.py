"""Agregar body_terms a news_index: frases del cuerpo para buscar (ADR-0014).

Los ngramas de GDELT traen frases de 4 palabras del texto completo de cada
nota. Se guardan normalizadas (mayúsculas, sin acentos, con Ñ), separadas
por `` | `` para que una búsqueda no junte palabras de dos frases distintas.
Sirven **solo para buscar**: nunca se muestran ni van a reportes, y se
borran a los ``NEWS_BODY_RETENTION_DAYS`` (30) aunque la nota siga.

Índice en la misma migración (CLAUDE.md §6.3): trigramas sobre
``body_terms``, el mismo tipo que ``text_norm``, para que las expresiones
de palabra completa no recorran toda la tabla.

Revisión: 0010
Anterior: 0009
Fecha: 2026-10-17
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Agrega la columna (vacía en las notas existentes) y su índice."""
    op.execute("ALTER TABLE news_index ADD COLUMN body_terms text")
    op.execute(
        "CREATE INDEX news_index_body_trgm ON news_index USING gin (body_terms gin_trgm_ops)"
    )


def downgrade() -> None:
    """Quita las frases del cuerpo (las notas se conservan)."""
    op.execute("DROP INDEX news_index_body_trgm")
    op.execute("ALTER TABLE news_index DROP COLUMN body_terms")
