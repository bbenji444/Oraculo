"""Crear casos, sus miembros, notas, entidades y notas del investigador (Fase 9.2).

Un caso es el contenedor de una investigación ("Homicidio estilista
Polanco"): agrupa noticias y entidades, y le da a cada entidad un rol y un
estado propios de ESE caso sin tocar la entidad global.

- ``cases``: nombre, estado (``open``/``closed``/``archived``) y nivel de
  sensibilidad (normal, reservado, confidencial). ``closed_at`` va con el
  estado: un caso abierto no tiene fecha de cierre y uno cerrado sí.
- ``case_members``: quién puede ver o editar el caso (§9.10). Hasta la Fase 8
  el usuario es el identificador de texto de desarrollo, el mismo de
  ``created_by``; la API aplica los permisos desde la 9.3. Un solo dueño.
- ``case_articles`` y ``case_entities``: lo que contiene el caso, con llaves
  foráneas reales (no una tabla genérica con tipo + id, que no impediría
  apuntar a una nota que no existe).
- ``case_notes``: notas del investigador, ancladas a lo más a una entidad,
  nota o vínculo. Si el ancla se borra, la nota se queda sin ancla.

Borrar un caso borra lo que es del caso (miembros, ítems, notas), nunca las
noticias ni las entidades, que son de todo el sistema.

Bitácora: ``audit_log`` no cambia de forma; ver un caso se registra como
``case.viewed`` (§9.10). Se agrega el índice por usuario para responder "qué
casos vio esta persona".

Índices en la misma migración (CLAUDE.md §6.3): (``status``, ``updated_at``,
``id``) para listar por cursor, el de "mis casos" y uno por cada llave
foránea que se consulta.

Revisión: 0019
Anterior: 0018
Fecha: 2026-10-20
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0019"
down_revision: str | None = "0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Crea las tablas y sus índices."""
    op.execute(
        """
        CREATE TABLE cases (
            id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            name         text NOT NULL,
            name_norm    text NOT NULL,
            description  text,
            status       text NOT NULL DEFAULT 'open',
            sensitivity  text NOT NULL DEFAULT 'normal',
            -- Usuario de desarrollo hasta F8 (igual que searches.user_id).
            created_by   text NOT NULL,
            closed_at    timestamptz,
            created_at   timestamptz NOT NULL DEFAULT now(),
            updated_at   timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT cases_name_not_blank CHECK (btrim(name) <> ''),
            CONSTRAINT cases_status_known CHECK (status IN ('open', 'closed', 'archived')),
            CONSTRAINT cases_sensitivity_known
                CHECK (sensitivity IN ('normal', 'restricted', 'confidential')),
            CONSTRAINT cases_closed_at_matches_status
                CHECK ((status = 'open') = (closed_at IS NULL))
        )
        """
    )
    op.execute("CREATE INDEX cases_status_updated_id ON cases (status, updated_at, id)")
    op.execute("CREATE INDEX cases_created_by ON cases (created_by)")

    op.execute(
        """
        CREATE TABLE case_members (
            case_id     uuid NOT NULL REFERENCES cases (id) ON DELETE CASCADE,
            user_id     text NOT NULL,
            role        text NOT NULL,
            added_by    text NOT NULL,
            created_at  timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (case_id, user_id),
            CONSTRAINT case_members_user_not_blank CHECK (btrim(user_id) <> ''),
            CONSTRAINT case_members_role_known CHECK (role IN ('owner', 'editor', 'viewer'))
        )
        """
    )
    op.execute("CREATE INDEX case_members_user_case ON case_members (user_id, case_id)")
    op.execute(
        "CREATE UNIQUE INDEX case_members_one_owner ON case_members (case_id) WHERE role = 'owner'"
    )

    op.execute(
        """
        CREATE TABLE case_articles (
            case_id     uuid NOT NULL REFERENCES cases (id) ON DELETE CASCADE,
            article_id  bigint NOT NULL REFERENCES articles (id) ON DELETE CASCADE,
            added_by    text NOT NULL,
            pinned      boolean NOT NULL DEFAULT false,
            note        text,
            created_at  timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (case_id, article_id)
        )
        """
    )
    op.execute("CREATE INDEX case_articles_article ON case_articles (article_id)")

    op.execute(
        """
        CREATE TABLE case_entities (
            case_id      uuid NOT NULL REFERENCES cases (id) ON DELETE CASCADE,
            entity_id    bigint NOT NULL REFERENCES entities (id) ON DELETE CASCADE,
            -- Rol en ESTE caso ("proveedor del salón"); no cambia la entidad global.
            case_role    text,
            case_status  text NOT NULL DEFAULT 'active',
            tag          text,
            added_by     text NOT NULL,
            created_at   timestamptz NOT NULL DEFAULT now(),
            updated_at   timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (case_id, entity_id),
            CONSTRAINT case_entities_status_known
                CHECK (case_status IN ('active', 'line_of_inquiry', 'ruled_out'))
        )
        """
    )
    op.execute("CREATE INDEX case_entities_entity ON case_entities (entity_id)")

    op.execute(
        """
        CREATE TABLE case_notes (
            id               bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            case_id          uuid NOT NULL REFERENCES cases (id) ON DELETE CASCADE,
            body             text NOT NULL,
            entity_id        bigint REFERENCES entities (id) ON DELETE SET NULL,
            article_id       bigint REFERENCES articles (id) ON DELETE SET NULL,
            relationship_id  bigint REFERENCES relationships (id) ON DELETE SET NULL,
            author           text NOT NULL,
            created_at       timestamptz NOT NULL DEFAULT now(),
            updated_at       timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT case_notes_body_not_blank CHECK (btrim(body) <> ''),
            CONSTRAINT case_notes_one_anchor
                CHECK (num_nonnulls(entity_id, article_id, relationship_id) <= 1)
        )
        """
    )
    op.execute("CREATE INDEX case_notes_case_created_id ON case_notes (case_id, created_at, id)")
    op.execute("CREATE INDEX case_notes_entity ON case_notes (entity_id)")
    op.execute("CREATE INDEX case_notes_article ON case_notes (article_id)")
    op.execute("CREATE INDEX case_notes_relationship ON case_notes (relationship_id)")

    # "Qué casos vio esta persona" (§9.10): la bitácora ya tenía índices por
    # fecha, entidad y acción, pero no por usuario.
    op.execute("CREATE INDEX audit_log_user_created ON audit_log (user_id, created_at)")


def downgrade() -> None:
    """Elimina las tablas de casos y el índice de la bitácora (no toca la bitácora)."""
    op.execute("DROP INDEX audit_log_user_created")
    op.execute("DROP TABLE case_notes")
    op.execute("DROP TABLE case_entities")
    op.execute("DROP TABLE case_articles")
    op.execute("DROP TABLE case_members")
    op.execute("DROP TABLE cases")
