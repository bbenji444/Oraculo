"""Casos de uso de la resolución de entidades de un caso (Fase 9.5, §9.8; ADR-0104).

La IA puede proponer a la misma persona varias veces ("Julián “N”" en una nota,
"Julián Ortega Ruiz" con el alias "Julián N" en otra). El sistema **sugiere**
qué entidades podrían ser la misma y una persona decide:

- ``ListMergeSuggestions``: los pares a revisar, con su motivo y cuál se
  propone que quede.
- ``MergeEntities``: «Son la misma» (o «Unir con…» a mano).
- ``DismissMerge``: «No son la misma»; el par no vuelve a salir.
- ``UnmergeEntity``: deshace una fusión.
- ``SplitEntity``: separa menciones de una sugerencia que juntó a dos
  personas con el mismo nombre.

Reglas que se cumplen aquí:

- **Nunca se fusiona solo:** ninguna lectura escribe ``merged_into``; solo
  ``MergeEntities``, que pide una persona con permiso de edición.
- Leer es para cualquier miembro del caso; unir, separar y descartar, para
  editores y dueños con el caso abierto (permisos de la 9.3).
- Cada decisión va a la bitácora con quién la tomó y qué quedó de cada
  entidad (CLAUDE.md §8).

No hace: no sabe de HTTP ni de SQL; no crea vínculos (``relationships``).
"""

from collections.abc import Sequence
from dataclasses import dataclass
from uuid import UUID

from app.application.audit import Actor, AuditEntry
from app.application.ports.cases import CaseRepositoryPort
from app.application.ports.entities import CaseEntity, EntityRepositoryPort, MergeSuggestion
from app.application.use_cases.cases import case_for, require_edit
from app.domain.entity_resolution import (
    MergeCandidate,
    MergeReason,
    check_merge,
    check_split,
    ordered_ids,
    strongest_reason,
)
from app.domain.errors import EntityMergeError, EntityNotFoundError
from app.domain.investigation import InvestigationAction, ReviewStatus


@dataclass(frozen=True, slots=True)
class MergeProposal:
    """Un par a revisar, listo para mostrarse lado a lado.

    Attributes:
        first: La de id menor.
        second: La de id mayor.
        reason: El motivo más seguro.
        reasons: Todos los motivos que cumple.
        keep_id: Cuál se propone que quede: la confirmada, si hay una; si no,
            la de más menciones; si empatan, la más antigua.
    """

    first: CaseEntity
    second: CaseEntity
    reason: MergeReason
    reasons: frozenset[MergeReason]
    keep_id: int


def _keep_first(first: CaseEntity, second: CaseEntity) -> bool:
    def weight(entity: CaseEntity) -> tuple[bool, int, int]:
        return (
            entity.review_status is ReviewStatus.CONFIRMED,
            len(entity.mentions),
            -entity.entity_id,
        )

    return weight(first) >= weight(second)


def _proposal(suggestion: MergeSuggestion) -> MergeProposal:
    first, second = suggestion.first, suggestion.second
    return MergeProposal(
        first=first,
        second=second,
        reason=strongest_reason(suggestion.reasons),
        reasons=suggestion.reasons,
        keep_id=first.entity_id if _keep_first(first, second) else second.entity_id,
    )


def _summary(entity: CaseEntity) -> dict[str, object]:
    return {
        "entity_id": entity.entity_id,
        "label": entity.label,
        "review_status": entity.review_status.value,
        "legal_status": entity.legal_status.value if entity.legal_status else None,
        "mentions": len(entity.mentions),
    }


class ListMergeSuggestions:
    """Pares de entidades del caso que podrían ser la misma."""

    def __init__(self, cases: CaseRepositoryPort, entities: EntityRepositoryPort) -> None:
        """Recibe los repositorios.

        Args:
            cases: Casos (para los permisos).
            entities: Entidades.
        """
        self._cases = cases
        self._entities = entities

    async def execute(self, case_id: UUID, actor: Actor) -> list[MergeProposal]:
        """Lista las sugerencias, las más seguras primero.

        Mirarlas no escribe nada: ni fusiona ni va a la bitácora (abrir el caso
        ya quedó como ``case.viewed``).

        Args:
            case_id: Caso.
            actor: Quién pregunta (cualquier miembro).

        Returns:
            Por motivo (mismo nombre, nombre o alias en común, nombre
            parecido), luego por tipo y nombre.

        Raises:
            CaseNotFoundError: Si el caso no existe o la persona no es miembro.
        """
        await case_for(self._cases, case_id, actor)
        proposals = [_proposal(s) for s in await self._entities.merge_suggestions(case_id)]
        rank = {reason: n for n, reason in enumerate(MergeReason)}
        return sorted(
            proposals,
            key=lambda p: (
                rank[p.reason],
                p.first.type.value,
                p.first.label.casefold(),
                p.first.entity_id,
                p.second.entity_id,
            ),
        )


async def _candidate(
    entities: EntityRepositoryPort, case_id: UUID, entity_id: int
) -> MergeCandidate:
    found = await entities.merge_candidate(case_id, entity_id)
    if found is None:
        raise EntityNotFoundError(
            "No existe esa entidad en el caso.", {"case_id": str(case_id), "entity_id": entity_id}
        )
    return found


async def _root(entities: EntityRepositoryPort, case_id: UUID, entity_id: int) -> CaseEntity:
    found = await entities.get_entity(case_id, entity_id)
    if found is None:
        raise EntityNotFoundError(
            "No existe esa entidad en el caso.", {"case_id": str(case_id), "entity_id": entity_id}
        )
    return found


class MergeEntities:
    """Une una entidad a otra porque una persona dijo que son la misma (D4)."""

    def __init__(self, cases: CaseRepositoryPort, entities: EntityRepositoryPort) -> None:
        """Recibe los repositorios.

        Args:
            cases: Casos (para los permisos).
            entities: Entidades.
        """
        self._cases = cases
        self._entities = entities

    async def execute(self, case_id: UUID, keep_id: int, merge_id: int, actor: Actor) -> CaseEntity:
        """Une ``merge_id`` a ``keep_id`` con firma y bitácora.

        Args:
            case_id: Caso.
            keep_id: La que queda (la confirmada, si una lo está).
            merge_id: La que se une a ella.
            actor: Quién decide.

        Returns:
            La que queda, con las menciones y alias de las dos.

        Raises:
            CaseNotFoundError: Si el caso no existe o la persona no es miembro.
            CaseForbiddenError: Si su rol solo permite mirar.
            CaseClosedError: Si el caso está cerrado o archivado.
            EntityNotFoundError: Si alguna no es de ese caso.
            EntityMergeError: Si la fusión no cumple sus reglas (``check_merge``).
        """
        require_edit(await case_for(self._cases, case_id, actor))
        check_merge(
            await _candidate(self._entities, case_id, keep_id),
            await _candidate(self._entities, case_id, merge_id),
        )
        keep = await _root(self._entities, case_id, keep_id)
        merge = await _root(self._entities, case_id, merge_id)
        audit = AuditEntry(
            actor,
            InvestigationAction.ENTITY_MERGED,
            {"keep": _summary(keep), "merged": _summary(merge), "type": keep.type.value},
        )
        return await self._entities.merge(case_id, keep_id, merge_id, audit)


class UnmergeEntity:
    """Deshace una fusión: la entidad vuelve a ser independiente (D5)."""

    def __init__(self, cases: CaseRepositoryPort, entities: EntityRepositoryPort) -> None:
        """Recibe los repositorios.

        Args:
            cases: Casos (para los permisos).
            entities: Entidades.
        """
        self._cases = cases
        self._entities = entities

    async def execute(self, case_id: UUID, entity_id: int, actor: Actor) -> CaseEntity:
        """Separa la entidad de aquella a la que se unió, con firma y bitácora.

        Args:
            case_id: Caso.
            entity_id: La entidad unida que se separa.
            actor: Quién decide.

        Returns:
            La entidad separada.

        Raises:
            CaseNotFoundError: Si el caso no existe o la persona no es miembro.
            CaseForbiddenError: Si su rol solo permite mirar.
            CaseClosedError: Si el caso está cerrado o archivado.
            EntityNotFoundError: Si no es de ese caso.
            EntityMergeError: Si no está unida a otra.
        """
        require_edit(await case_for(self._cases, case_id, actor))
        candidate = await _candidate(self._entities, case_id, entity_id)
        if candidate.merged_into is None:
            raise EntityMergeError("Esa entidad no está unida a otra.", {"entity_id": entity_id})
        audit = AuditEntry(
            actor,
            InvestigationAction.ENTITY_UNMERGED,
            {"entity_id": entity_id, "was_merged_into": candidate.merged_into},
        )
        return await self._entities.unmerge(case_id, entity_id, audit)


class SplitEntity:
    """Separa menciones de una entidad en una sugerencia nueva (D5)."""

    def __init__(self, cases: CaseRepositoryPort, entities: EntityRepositoryPort) -> None:
        """Recibe los repositorios.

        Args:
            cases: Casos (para los permisos).
            entities: Entidades.
        """
        self._cases = cases
        self._entities = entities

    async def execute(
        self, case_id: UUID, entity_id: int, mention_ids: Sequence[int], actor: Actor
    ) -> CaseEntity:
        """Pasa esas menciones a una sugerencia nueva, con firma y bitácora.

        Sirve cuando la agrupación por nombre juntó a dos personas distintas.
        La nueva nace sugerida: hay que revisarla como cualquier otra.

        Args:
            case_id: Caso.
            entity_id: Entidad de donde salen (no unida a otra).
            mention_ids: Menciones propias que se separan.
            actor: Quién decide.

        Returns:
            La entidad nueva.

        Raises:
            CaseNotFoundError: Si el caso no existe o la persona no es miembro.
            CaseForbiddenError: Si su rol solo permite mirar.
            CaseClosedError: Si el caso está cerrado o archivado.
            EntityNotFoundError: Si la entidad no es de ese caso o está unida
                a otra.
            EntityMergeError: Si las menciones no cumplen ``check_split``.
        """
        require_edit(await case_for(self._cases, case_id, actor))
        entity = await _root(self._entities, case_id, entity_id)
        check_split(mention_ids, entity.own_mention_ids)
        audit = AuditEntry(
            actor,
            InvestigationAction.ENTITY_SPLIT,
            {
                "entity_id": entity_id,
                "label": entity.label,
                "mention_ids": sorted(set(mention_ids)),
            },
        )
        return await self._entities.split(case_id, entity_id, mention_ids, audit)


class DismissMerge:
    """Guarda que dos entidades no son la misma: el par deja de sugerirse (D3)."""

    def __init__(self, cases: CaseRepositoryPort, entities: EntityRepositoryPort) -> None:
        """Recibe los repositorios.

        Args:
            cases: Casos (para los permisos).
            entities: Entidades.
        """
        self._cases = cases
        self._entities = entities

    async def execute(self, case_id: UUID, first_id: int, second_id: int, actor: Actor) -> bool:
        """Descarta la sugerencia con firma y bitácora.

        Args:
            case_id: Caso.
            first_id: Una entidad del par.
            second_id: La otra.
            actor: Quién decide.

        Returns:
            ``True`` si se guardó; ``False`` si ya estaba descartado.

        Raises:
            CaseNotFoundError: Si el caso no existe o la persona no es miembro.
            CaseForbiddenError: Si su rol solo permite mirar.
            CaseClosedError: Si el caso está cerrado o archivado.
            EntityNotFoundError: Si alguna no es de ese caso.
            EntityMergeError: Si es la misma entidad.
        """
        require_edit(await case_for(self._cases, case_id, actor))
        low, high = ordered_ids(first_id, second_id)
        first = await _root(self._entities, case_id, low)
        second = await _root(self._entities, case_id, high)
        audit = AuditEntry(
            actor,
            InvestigationAction.ENTITY_MERGE_DISMISSED,
            {"first": _summary(first), "second": _summary(second)},
        )
        return await self._entities.dismiss_merge(case_id, low, high, audit)
