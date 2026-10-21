"""Vocabulario del tablero de investigación (Fase 9; ADR-0101, 0104 y 0105).

Los valores de cada enum son los mismos que aceptan los CHECK de las tablas
de las migraciones 0018 (entidades, menciones y vínculos) y 0019 (casos); las
pruebas de integración comprueban que no se separen. Las etiquetas en español
son las que verá el analista.

Reglas que fija este módulo:

- **Nada propuesto nace confirmado:** una entidad o un vínculo empieza como
  ``ReviewStatus.SUGGESTED`` y solo una persona lo confirma o lo descarta
  (ADR-0104).
- **El estatus legal es lo que afirma la nota**, nunca una conclusión del
  sistema: no existe "culpable" (ADR-0105).
- **Los vínculos simétricos** ("aparecen juntas", "mismo hecho"…) se guardan
  con el id menor primero, para que A–B y B–A sean el mismo vínculo
  (``ordered_pair``).

Quién lo usa: los casos de uso de casos, entidades y vínculos (desde la 9.3) y
las pruebas de las tablas.

No hace: no guarda ni consulta nada, y no decide si dos personas son la misma
(eso lo confirma un humano en la 9.5).
"""

from enum import StrEnum

from app.domain.errors import InvalidRequestError

# Decisión D8 de la 9.2: la evidencia es una cita corta de la nota, nunca el
# artículo (CLAUDE.md §8). Sobrevive al borrado del texto a los 30 días
# (ADR-0015), así que es lo único que prueba de dónde salió una entidad.
EVIDENCE_SPAN_MAX_CHARS = 300


class EntityType(StrEnum):
    """Columna ``entities.type``."""

    PERSON = "person"
    ORG = "org"
    PLACE = "place"
    VEHICLE = "vehicle"
    ACCOUNT = "account"
    PHONE = "phone"
    OTHER = "other"


ENTITY_TYPE_LABEL: dict[EntityType, str] = {
    EntityType.PERSON: "persona",
    EntityType.ORG: "organización",
    EntityType.PLACE: "lugar",
    EntityType.VEHICLE: "vehículo",
    EntityType.ACCOUNT: "cuenta",
    EntityType.PHONE: "teléfono",
    EntityType.OTHER: "otro",
}


class LegalStatus(StrEnum):
    """Columnas ``entities.legal_status`` y ``entity_mentions.legal_status_hint``.

    Solo personas. Refleja lo que dice la nota ("fue detenido" → ``DETAINED``);
    si la nota no lo dice, queda vacío. A propósito no hay "culpable".
    """

    MENTIONED = "mentioned"
    ALLEGED = "alleged"
    DETAINED = "detained"
    # Agregado en la 9.2 a lo que pedía el plan: en las notas mexicanas
    # "vinculado a proceso" es frecuente y no es lo mismo que detenido.
    CHARGED = "charged"
    VICTIM = "victim"
    WITNESS = "witness"
    OFFICIAL = "official"


LEGAL_STATUS_LABEL: dict[LegalStatus, str] = {
    LegalStatus.MENTIONED: "mencionado",
    LegalStatus.ALLEGED: "señalado",
    LegalStatus.DETAINED: "detenido",
    LegalStatus.CHARGED: "vinculado a proceso",
    LegalStatus.VICTIM: "víctima",
    LegalStatus.WITNESS: "testigo",
    LegalStatus.OFFICIAL: "funcionario",
}


class ReviewStatus(StrEnum):
    """Columna ``review_status`` de entidades y vínculos (ADR-0104)."""

    SUGGESTED = "suggested"
    CONFIRMED = "confirmed"
    DISCARDED = "discarded"


REVIEW_STATUS_LABEL: dict[ReviewStatus, str] = {
    ReviewStatus.SUGGESTED: "sugerido",
    ReviewStatus.CONFIRMED: "confirmado",
    ReviewStatus.DISCARDED: "descartado",
}

# Todo lo que proponen la IA o la coocurrencia empieza aquí (ADR-0104).
INITIAL_REVIEW_STATUS = ReviewStatus.SUGGESTED


class Origin(StrEnum):
    """Columna ``relationships.origin``: quién propuso el vínculo (ADR-0105)."""

    COOCCURRENCE = "cooccurrence"
    LLM = "llm"
    HUMAN = "human"


ORIGIN_LABEL: dict[Origin, str] = {
    Origin.COOCCURRENCE: "aparecen en la misma nota",
    Origin.LLM: "propuesto por la IA",
    Origin.HUMAN: "dibujado por una persona",
}


class RelationshipType(StrEnum):
    """Columna ``relationships.type``."""

    APPEARS_WITH = "appears_with"
    SAME_EVENT = "same_event"
    FAMILY = "family"
    ASSOCIATE = "associate"
    EMPLOYER = "employer"
    LOCATED_IN = "located_in"
    OWNS = "owns"
    CUSTOM = "custom"


RELATIONSHIP_LABEL: dict[RelationshipType, str] = {
    RelationshipType.APPEARS_WITH: "aparecen juntas",
    RelationshipType.SAME_EVENT: "mismo hecho",
    RelationshipType.FAMILY: "familiar",
    RelationshipType.ASSOCIATE: "asociado",
    RelationshipType.EMPLOYER: "empleador",
    RelationshipType.LOCATED_IN: "ubicado en",
    RelationshipType.OWNS: "es dueño de",
    RelationshipType.CUSTOM: "otro (etiqueta propia)",
}

# Vínculos sin sentido: A–B es lo mismo que B–A. Los demás van de A hacia B
# ("A es dueño de B").
SYMMETRIC_RELATIONSHIPS = frozenset(
    {
        RelationshipType.APPEARS_WITH,
        RelationshipType.SAME_EVENT,
        RelationshipType.FAMILY,
        RelationshipType.ASSOCIATE,
    }
)


def ordered_pair(kind: RelationshipType, entity_a: int, entity_b: int) -> tuple[int, int]:
    """Orden en que se guardan las dos entidades de un vínculo.

    En los vínculos simétricos va primero el id menor, para que la llave única
    (``entity_a``, ``entity_b``, ``type``) no deje guardar A–B y B–A como dos
    vínculos distintos. En los dirigidos se respeta el sentido.

    Args:
        kind: Tipo de vínculo.
        entity_a: Primera entidad, como la eligió la persona.
        entity_b: Segunda entidad.

    Returns:
        Las dos entidades en el orden en que se guardan.

    Raises:
        InvalidRequestError: Si las dos son la misma entidad.

    Example:
        >>> ordered_pair(RelationshipType.SAME_EVENT, 9, 4)
        (4, 9)
    """
    if entity_a == entity_b:
        raise InvalidRequestError(
            "Una entidad no se puede vincular consigo misma.", {"entity_id": entity_a}
        )
    if kind in SYMMETRIC_RELATIONSHIPS:
        return min(entity_a, entity_b), max(entity_a, entity_b)
    return entity_a, entity_b


class CaseStatus(StrEnum):
    """Columna ``cases.status``."""

    OPEN = "open"
    CLOSED = "closed"
    ARCHIVED = "archived"


CASE_STATUS_LABEL: dict[CaseStatus, str] = {
    CaseStatus.OPEN: "abierto",
    CaseStatus.CLOSED: "cerrado",
    CaseStatus.ARCHIVED: "archivado",
}


class Sensitivity(StrEnum):
    """Columna ``cases.sensitivity``: nivel de reserva del caso (§9.10)."""

    NORMAL = "normal"
    RESTRICTED = "restricted"
    CONFIDENTIAL = "confidential"


SENSITIVITY_LABEL: dict[Sensitivity, str] = {
    Sensitivity.NORMAL: "normal",
    Sensitivity.RESTRICTED: "reservado",
    Sensitivity.CONFIDENTIAL: "confidencial",
}


class CaseMemberRole(StrEnum):
    """Columna ``case_members.role``: qué puede hacer cada persona en el caso.

    Hasta la Fase 8 el usuario es el identificador de texto de desarrollo
    (``DEV_USER``), el mismo de ``created_by``; la 9.3 aplica estos permisos en
    la API.
    """

    OWNER = "owner"
    EDITOR = "editor"
    VIEWER = "viewer"


CASE_MEMBER_ROLE_LABEL: dict[CaseMemberRole, str] = {
    CaseMemberRole.OWNER: "dueño",
    CaseMemberRole.EDITOR: "editor",
    CaseMemberRole.VIEWER: "lector",
}


class CaseEntityStatus(StrEnum):
    """Columna ``case_entities.case_status``: cómo ve el analista a la entidad en ESTE caso."""

    ACTIVE = "active"
    LINE_OF_INQUIRY = "line_of_inquiry"
    RULED_OUT = "ruled_out"


CASE_ENTITY_STATUS_LABEL: dict[CaseEntityStatus, str] = {
    CaseEntityStatus.ACTIVE: "en el caso",
    CaseEntityStatus.LINE_OF_INQUIRY: "línea de investigación",
    CaseEntityStatus.RULED_OUT: "descartada en el caso",
}


class InvestigationAction(StrEnum):
    """Acciones de la bitácora (``audit_log.action``) del tablero (§9.10).

    Ver un caso cuenta igual que editarlo: en una herramienta así importa
    quién miró qué.
    """

    CASE_CREATED = "case.created"
    CASE_UPDATED = "case.updated"
    CASE_CLOSED = "case.closed"
    CASE_ARCHIVED = "case.archived"
    CASE_REOPENED = "case.reopened"
    CASE_VIEWED = "case.viewed"
    CASE_MEMBER_ADDED = "case.member_added"
    CASE_MEMBER_REMOVED = "case.member_removed"
    CASE_ARTICLE_ADDED = "case.article_added"
    CASE_ARTICLE_REMOVED = "case.article_removed"
    CASE_ENTITY_ADDED = "case.entity_added"
    # La IA leyó una nota del caso (9.4): con su modelo, tokens y costo, o el error.
    CASE_ENTITIES_EXTRACTED = "case.entities_extracted"
    CASE_NOTE_ADDED = "case.note_added"
    ENTITY_CONFIRMED = "entity.confirmed"
    ENTITY_DISCARDED = "entity.discarded"
    ENTITY_MERGED = "entity.merged"
    # Fase 9.5: deshacer una fusión, separar menciones de una sugerencia y
    # decir que dos entidades no son la misma también llevan firma.
    ENTITY_UNMERGED = "entity.unmerged"
    ENTITY_SPLIT = "entity.split"
    ENTITY_MERGE_DISMISSED = "entity.merge_dismissed"
    RELATIONSHIP_CREATED = "relationship.created"
    RELATIONSHIP_CONFIRMED = "relationship.confirmed"
    RELATIONSHIP_DISCARDED = "relationship.discarded"
