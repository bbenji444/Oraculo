"""Cómo se lee la bitácora de auditoría en «Accesos» (especificación §16).

La bitácora (``audit_log``) guarda quién hizo qué: entradas, llaves vistas o
generadas, búsquedas, reportes, casos y conceptos. Aquí se define cómo se
agrupa para la pantalla y cómo se ve cada registro.

Las acciones tienen la forma ``<tema>.<verbo>`` (``access_key.revealed``):
lo de antes del punto decide en qué grupo cae.

No hace: no lee la base ni decide quién puede verla (eso es de
``app.application.use_cases.audit_trail``).
"""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

# 50 registros por página llenan la pantalla sin hacerla pesada; el tope
# evita que alguien pida la tabla entera de un jalón.
DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 200


class AuditGroup(StrEnum):
    """Grupos de la bitácora en la pantalla."""

    ALL = "all"
    ACCESS = "access"
    SEARCHES = "searches"
    REPORTS = "reports"
    CASES = "cases"
    CONCEPTS = "concepts"


# Lo de antes del punto en ``audit_log.action``, por grupo. Sale de las
# constantes de acciones de los casos de uso (access, login, cases,
# entities, relationships) y de ``app.application.audit``.
GROUP_PREFIXES: Mapping[AuditGroup, tuple[str, ...]] = {
    AuditGroup.ALL: (),
    AuditGroup.ACCESS: ("auth", "user", "access_key"),
    AuditGroup.SEARCHES: ("search", "provider", "schedule"),
    AuditGroup.REPORTS: ("report",),
    AuditGroup.CASES: ("case", "entity", "entities", "relationship"),
    AuditGroup.CONCEPTS: ("concept", "category"),
}


@dataclass(frozen=True, slots=True)
class AuditEvent:
    """Un registro de la bitácora, tal como lo ve un superusuario.

    Attributes:
        event_id: Id del registro (crece con el tiempo: sirve de cursor).
        created_at: Cuándo pasó (UTC).
        actor: Usuario que lo hizo, o quién lo hizo si no fue una persona
            (``consola``, ``semilla``, ``anonimo``).
        actor_name: Nombre de esa persona en «Accesos», si existe.
        action: Qué pasó (``access_key.revealed``).
        entity_type: Sobre qué (``access_key``, ``search``, ``case``...).
        entity_id: Id de eso, como texto; vacío si no aplica.
        payload: Datos del registro, como se guardaron. Nunca trae secretos:
            las llaves van enmascaradas (``orc_live_a1b2c3d4…``).
        ip: Desde dónde, o ``None`` si no vino de una petición HTTP.
    """

    event_id: int
    created_at: datetime
    actor: str
    actor_name: str | None
    action: str
    entity_type: str
    entity_id: str
    payload: Mapping[str, object]
    ip: str | None


@dataclass(frozen=True, slots=True)
class AuditQuery:
    """Qué parte de la bitácora se quiere ver.

    Attributes:
        group: Grupo de acciones (``ALL`` es todo).
        actor: Solo lo que hizo este usuario; ``None`` es de todos.
        before: Solo registros con id menor (la página siguiente).
        limit: Cuántos como máximo.
    """

    group: AuditGroup = AuditGroup.ALL
    actor: str | None = None
    before: int | None = None
    limit: int = DEFAULT_PAGE_SIZE

    @property
    def prefixes(self) -> tuple[str, ...]:
        """Los temas de acción del grupo; vacío si es todo."""
        return GROUP_PREFIXES[self.group]

    @property
    def size(self) -> int:
        """``limit`` dentro de 1 y ``MAX_PAGE_SIZE``."""
        return min(max(self.limit, 1), MAX_PAGE_SIZE)


@dataclass(frozen=True, slots=True)
class AuditPage:
    """Una página de la bitácora, de lo más nuevo a lo más viejo.

    Attributes:
        events: Los registros de la página.
        next_before: Cursor de la página siguiente; ``None`` si ya no hay más.
    """

    events: tuple[AuditEvent, ...]
    next_before: int | None
