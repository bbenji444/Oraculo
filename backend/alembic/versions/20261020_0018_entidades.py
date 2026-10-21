"""Crear entidades, alias, menciones, vínculos y ``external_links`` (Fase 9.2).

El tablero de investigación trata a personas, organizaciones, lugares y
vehículos como objetos propios que tienen fuentes (ADR-0101). Hoy su única
fuente son las notas; mañana, las bases del sistema Oráculo.

- ``entities``: el objeto. Las personas llevan estatus legal, que es lo que
  dice la nota y nunca "culpable" (ADR-0105). Todo nace ``suggested`` y solo
  una persona lo confirma o lo descarta, con su nombre y la hora (ADR-0104).
  Los lugares se ligan al catálogo (``regions`` o ``places``): su punto sale
  de ahí, nunca de la IA (§11).
- ``entity_aliases``: otros nombres ("Eduardo N", "Micky Hair").
- ``entity_mentions``: la evidencia. De qué nota salió la entidad y con qué
  cita corta (máximo 300 caracteres): sobrevive al borrado del texto de la
  nota a los 30 días (ADR-0015) y nunca es el artículo (CLAUDE.md §8).
- ``relationships``: vínculos entre dos entidades con su origen (coocurrencia,
  IA o humano) y su confianza. Únicos por par y tipo; los simétricos se
  guardan con el id menor primero (``domain.investigation.ordered_pair``).
- ``external_links``: **reservada y vacía**. Es el enchufe futuro hacia
  registros de otras bases; ninguna lógica de la Fase 9 la lee ni la escribe
  (una prueba de arquitectura lo vigila).

Los valores permitidos son los de ``app.domain.investigation``; las pruebas de
``test_investigation_tables.py`` comprueban que no se separen.

Índices en la misma migración (CLAUDE.md §6.3): trigramas de ``label_norm`` y
``alias_norm`` (sugerir fusiones en la 9.5), (``type``, ``review_status``,
``id``) para listar por cursor, y uno por cada llave foránea que se consulta.

Revisión: 0018
Anterior: 0017
Fecha: 2026-10-20
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0018"
down_revision: str | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Valores de app.domain.investigation (aquí escritos: una migración no debe
# cambiar si el código cambia después).
_LEGAL_STATUSES = "'mentioned', 'alleged', 'detained', 'charged', 'victim', 'witness', 'official'"
_REVIEW_STATUSES = "'suggested', 'confirmed', 'discarded'"
# Decisión D8 de la 9.2 (EVIDENCE_SPAN_MAX_CHARS).
_EVIDENCE_SPAN_MAX_CHARS = 300


def upgrade() -> None:
    """Crea las tablas y sus índices."""
    op.execute(
        f"""
        CREATE TABLE entities (
            id               bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            type             text NOT NULL,
            canonical_label  text NOT NULL,
            label_norm       text NOT NULL,
            -- Solo personas: lo que afirma la nota (ADR-0105). Nulo si no lo dice.
            legal_status     text,
            review_status    text NOT NULL DEFAULT 'suggested',
            reviewed_by      text,
            reviewed_at      timestamptz,
            -- Resolución de entidades (9.5): esta quedó fusionada en otra.
            merged_into      bigint REFERENCES entities (id),
            -- Solo lugares: dónde está en el catálogo (el punto sale de ahí).
            region_id        bigint REFERENCES regions (id),
            place_id         bigint REFERENCES places (id),
            notes            text,
            created_at       timestamptz NOT NULL DEFAULT now(),
            updated_at       timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT entities_type_known CHECK (
                type IN ('person', 'org', 'place', 'vehicle', 'account', 'phone', 'other')
            ),
            CONSTRAINT entities_label_not_blank CHECK (btrim(canonical_label) <> ''),
            CONSTRAINT entities_legal_status_known
                CHECK (legal_status IS NULL OR legal_status IN ({_LEGAL_STATUSES})),
            CONSTRAINT entities_legal_status_only_people
                CHECK (legal_status IS NULL OR type = 'person'),
            CONSTRAINT entities_catalog_only_places
                CHECK ((region_id IS NULL AND place_id IS NULL) OR type = 'place'),
            CONSTRAINT entities_review_status_known
                CHECK (review_status IN ({_REVIEW_STATUSES})),
            CONSTRAINT entities_review_signed CHECK (
                review_status = 'suggested'
                OR (reviewed_by IS NOT NULL AND reviewed_at IS NOT NULL)
            ),
            CONSTRAINT entities_not_merged_into_itself CHECK (merged_into <> id)
        )
        """
    )
    op.execute("CREATE INDEX entities_label_trgm ON entities USING gin (label_norm gin_trgm_ops)")
    op.execute("CREATE INDEX entities_type_review_id ON entities (type, review_status, id)")
    op.execute("CREATE INDEX entities_merged_into ON entities (merged_into)")
    op.execute("CREATE INDEX entities_region ON entities (region_id)")
    op.execute("CREATE INDEX entities_place ON entities (place_id)")

    op.execute(
        """
        CREATE TABLE entity_aliases (
            id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            entity_id   bigint NOT NULL REFERENCES entities (id) ON DELETE CASCADE,
            alias       text NOT NULL,
            alias_norm  text NOT NULL,
            created_at  timestamptz NOT NULL DEFAULT now(),
            UNIQUE (entity_id, alias_norm),
            CONSTRAINT entity_aliases_not_blank CHECK (btrim(alias) <> '')
        )
        """
    )
    op.execute(
        "CREATE INDEX entity_aliases_alias_trgm ON entity_aliases "
        "USING gin (alias_norm gin_trgm_ops)"
    )

    op.execute(
        f"""
        CREATE TABLE entity_mentions (
            id                 bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            entity_id          bigint NOT NULL REFERENCES entities (id) ON DELETE CASCADE,
            article_id         bigint NOT NULL REFERENCES articles (id) ON DELETE CASCADE,
            mention_text       text NOT NULL,
            role               text NOT NULL,
            legal_status_hint  text,
            confidence         real NOT NULL,
            -- Cita corta de la nota: la evidencia que sobrevive al texto (ADR-0015).
            evidence_span      text NOT NULL,
            -- Posición en el texto extraído; solo sirve mientras el texto exista.
            char_start         integer,
            char_end           integer,
            -- Modelo de IA (o "humano:<usuario>") y versión del prompt.
            extracted_by       text NOT NULL,
            prompt_version     text,
            created_at         timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT entity_mentions_role_known CHECK (role IN ('event', 'mentioned')),
            CONSTRAINT entity_mentions_legal_status_hint_known
                CHECK (legal_status_hint IS NULL OR legal_status_hint IN ({_LEGAL_STATUSES})),
            CONSTRAINT entity_mentions_confidence_range
                CHECK (confidence >= 0 AND confidence <= 1),
            CONSTRAINT entity_mentions_evidence_span_short CHECK (
                btrim(evidence_span) <> ''
                AND char_length(evidence_span) <= {_EVIDENCE_SPAN_MAX_CHARS}
            ),
            CONSTRAINT entity_mentions_char_span_valid CHECK (
                (char_start IS NULL AND char_end IS NULL)
                OR (char_start >= 0 AND char_end > char_start)
            )
        )
        """
    )
    op.execute("CREATE INDEX entity_mentions_entity ON entity_mentions (entity_id)")
    op.execute(
        "CREATE INDEX entity_mentions_article_entity ON entity_mentions (article_id, entity_id)"
    )

    op.execute(
        f"""
        CREATE TABLE relationships (
            id             bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            entity_a       bigint NOT NULL REFERENCES entities (id) ON DELETE CASCADE,
            entity_b       bigint NOT NULL REFERENCES entities (id) ON DELETE CASCADE,
            type           text NOT NULL,
            custom_label   text,
            origin         text NOT NULL,
            confidence     real NOT NULL,
            review_status  text NOT NULL DEFAULT 'suggested',
            reviewed_by    text,
            reviewed_at    timestamptz,
            notes          text,
            created_at     timestamptz NOT NULL DEFAULT now(),
            updated_at     timestamptz NOT NULL DEFAULT now(),
            UNIQUE (entity_a, entity_b, type),
            CONSTRAINT relationships_two_entities CHECK (entity_a <> entity_b),
            CONSTRAINT relationships_type_known CHECK (
                type IN ('appears_with', 'same_event', 'family', 'associate', 'employer',
                         'located_in', 'owns', 'custom')
            ),
            CONSTRAINT relationships_custom_label_only_custom CHECK (
                (type = 'custom') = (custom_label IS NOT NULL AND btrim(custom_label) <> '')
            ),
            CONSTRAINT relationships_origin_known
                CHECK (origin IN ('cooccurrence', 'llm', 'human')),
            CONSTRAINT relationships_confidence_range
                CHECK (confidence >= 0 AND confidence <= 1),
            CONSTRAINT relationships_review_status_known
                CHECK (review_status IN ({_REVIEW_STATUSES})),
            CONSTRAINT relationships_review_signed CHECK (
                review_status = 'suggested'
                OR (reviewed_by IS NOT NULL AND reviewed_at IS NOT NULL)
            )
        )
        """
    )
    op.execute("CREATE INDEX relationships_entity_b ON relationships (entity_b)")
    op.execute("CREATE INDEX relationships_review_id ON relationships (review_status, id)")

    op.execute(
        """
        CREATE TABLE external_links (
            id               bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            entity_id        bigint NOT NULL REFERENCES entities (id) ON DELETE CASCADE,
            external_system  text NOT NULL,
            external_ref     text NOT NULL,
            link_confidence  real,
            linked_by        text NOT NULL,
            created_at       timestamptz NOT NULL DEFAULT now(),
            UNIQUE (external_system, external_ref, entity_id),
            CONSTRAINT external_links_confidence_range
                CHECK (link_confidence IS NULL OR (link_confidence >= 0 AND link_confidence <= 1))
        )
        """
    )
    op.execute("CREATE INDEX external_links_entity ON external_links (entity_id)")
    op.execute(
        "COMMENT ON TABLE external_links IS 'Reservada, sin uso en la Fase 9 (ADR-0101): "
        "enchufe futuro de una entidad hacia un registro de otra base del sistema Oráculo. "
        "Ninguna lógica la lee ni la escribe.'"
    )


def downgrade() -> None:
    """Elimina las tablas (se pierden entidades, menciones y vínculos)."""
    op.execute("DROP TABLE external_links")
    op.execute("DROP TABLE relationships")
    op.execute("DROP TABLE entity_mentions")
    op.execute("DROP TABLE entity_aliases")
    op.execute("DROP TABLE entities")
