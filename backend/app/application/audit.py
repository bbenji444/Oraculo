"""Bitácora de auditoría: quién hizo qué (especificación §16, CLAUDE.md §8).

Los casos de uso deciden **qué** se registra y con qué datos; el repositorio
lo guarda en la misma transacción que el cambio, para que nunca quede un
cambio sin su registro ni un registro sin su cambio.

No hace: no escribe en la base (eso lo hacen los repositorios).
"""

from collections.abc import Mapping
from dataclasses import dataclass

from app.domain.concept import ConceptDraft

# Acciones estables en inglés: otros sistemas pueden filtrar por ellas.
CONCEPT_CREATED = "concept.created"
CONCEPT_UPDATED = "concept.updated"
CONCEPT_DELETED = "concept.deleted"


@dataclass(frozen=True, slots=True)
class Actor:
    """Quién hace el cambio.

    Attributes:
        user_id: Usuario (``DEV_USER`` hasta F8; ``semilla`` en ``make seed``).
        ip: IP de la petición, o ``None`` si no vino por HTTP.
    """

    user_id: str
    ip: str | None = None


@dataclass(frozen=True, slots=True)
class AuditEntry:
    """Un registro para la bitácora. El repositorio agrega la entidad y su id.

    Attributes:
        actor: Quién.
        action: Qué (``concept.created``...).
        payload: Datos del cambio, por ejemplo ``{"before": ..., "after": ...}``.
    """

    actor: Actor
    action: str
    payload: Mapping[str, object]


def concept_snapshot(data: ConceptDraft) -> dict[str, object]:
    """Foto de un concepto para la bitácora (listas JSON, no tuplas).

    Args:
        data: Datos del concepto.

    Returns:
        Diccionario serializable a JSON.
    """
    return {
        "name": data.name,
        "description": data.description,
        "keywords": list(data.keywords),
        "exclude_terms": list(data.exclude_terms),
        "color": data.color,
        "is_active": data.is_active,
    }
