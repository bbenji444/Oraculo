"""Casos de uso de los vínculos entre entidades de un caso (Fase 9.5, D6 a D9).

- ``ListRelationships``: los vínculos del caso en un estado, con las notas que
  los sostienen.
- ``ReviewRelationship``: confirmar o descartar un vínculo sugerido (por
  ejemplo, «aparecen juntas» derivado de la coocurrencia).
- ``ReviewRelationships``: confirmar o descartar varios a la vez (F12,
  ADR-0107), todos o ninguno.
- ``CreateRelationship``: el analista dibuja un vínculo que el sistema no vio
  ("familiar", "es dueño de", una etiqueta propia).

Reglas que se cumplen aquí:

- Solo entre entidades **confirmadas** del caso: solo lo confirmado llega al
  muro (ADR-0104).
- Lo derivado nace sugerido; lo que dibuja una persona nace confirmado con su
  firma y confianza 1 (D7).
- Leer es para cualquier miembro; revisar y crear, para editores y dueños con
  el caso abierto. Cada decisión va a la bitácora.

No hace: no sabe de HTTP ni SQL; no propone vínculos con la IA.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from uuid import UUID

from app.application.audit import Actor, AuditEntry
from app.application.ports.cases import CaseRepositoryPort
from app.application.ports.entities import CaseEntity, EntityRepositoryPort
from app.application.ports.relationships import (
    RelationshipKey,
    RelationshipRepositoryPort,
    RelationshipView,
    RelationshipWrite,
    find,
)
from app.application.use_cases.cases import case_for, require_edit
from app.domain.bulk_review import BulkReviewResult, check_bulk_review
from app.domain.errors import RelationshipNotFoundError, RelationshipValidationError
from app.domain.investigation import (
    InvestigationAction,
    Origin,
    ReviewStatus,
    ordered_pair,
)
from app.domain.relationships import HUMAN_RELATIONSHIP_CONFIDENCE, manual_relationship


@dataclass(frozen=True, slots=True)
class CaseRelationships:
    """Lo que muestra la sección Vínculos de un caso.

    Attributes:
        counts: Cuántos vínculos hay en cada estado.
        items: Los del estado pedido, los de más confianza primero.
    """

    counts: dict[ReviewStatus, int]
    items: tuple[RelationshipView, ...]


@dataclass(frozen=True, slots=True)
class RelationshipInput:
    """Un vínculo que dibuja el analista, tal como llega.

    Attributes:
        entity_a: Primera entidad (en los dirigidos, la que "es dueño de").
        entity_b: Segunda entidad.
        type: Código del tipo de vínculo.
        custom_label: Etiqueta propia (solo ``custom``).
        notes: Nota opcional.
    """

    entity_a: int
    entity_b: int
    type: str
    custom_label: str | None = None
    notes: str | None = None


def _payload(view: RelationshipView) -> dict[str, object]:
    return {
        "entity_a": {"entity_id": view.entity_a.entity_id, "label": view.entity_a.label},
        "entity_b": {"entity_id": view.entity_b.entity_id, "label": view.entity_b.label},
        "type": view.type.value,
        "custom_label": view.custom_label,
        "origin": view.origin.value,
        "confidence": view.confidence,
        "shared_articles": len(view.shared_articles),
    }


class ListRelationships:
    """Vínculos de un caso en un estado de revisión."""

    def __init__(
        self, cases: CaseRepositoryPort, relationships: RelationshipRepositoryPort
    ) -> None:
        """Recibe los repositorios.

        Args:
            cases: Casos (para los permisos).
            relationships: Vínculos.
        """
        self._cases = cases
        self._relationships = relationships

    async def execute(self, case_id: UUID, actor: Actor, status: ReviewStatus) -> CaseRelationships:
        """Lista los vínculos del caso en ese estado.

        Mirarlos no escribe nada (abrir el caso ya quedó como ``case.viewed``).

        Args:
            case_id: Caso.
            actor: Quién pregunta (cualquier miembro).
            status: Sugeridos, confirmados o descartados.

        Returns:
            Conteos y vínculos, los de más confianza y más notas primero.

        Raises:
            CaseNotFoundError: Si el caso no existe o la persona no es miembro.
        """
        await case_for(self._cases, case_id, actor)
        views = await self._relationships.list_case(case_id)
        items = sorted(
            (v for v in views if v.review_status is status),
            key=lambda v: (
                -v.confidence,
                -len(v.shared_articles),
                v.entity_a.label.casefold(),
                v.entity_b.label.casefold(),
            ),
        )
        return CaseRelationships(
            counts={s: sum(1 for v in views if v.review_status is s) for s in ReviewStatus},
            items=tuple(items),
        )


class ReviewRelationship:
    """Confirma o descarta un vínculo sugerido, con firma y bitácora."""

    def __init__(
        self, cases: CaseRepositoryPort, relationships: RelationshipRepositoryPort
    ) -> None:
        """Recibe los repositorios.

        Args:
            cases: Casos (para los permisos).
            relationships: Vínculos.
        """
        self._cases = cases
        self._relationships = relationships

    async def execute(
        self, case_id: UUID, key: RelationshipKey, status: ReviewStatus, actor: Actor
    ) -> tuple[RelationshipView, bool]:
        """Revisa el vínculo con esa llave.

        Args:
            case_id: Caso.
            key: Entidades y tipo, como los devolvió la lista.
            status: Confirmado o descartado.
            actor: Quién decide.

        Returns:
            El vínculo como quedó y si cambió (revisar dos veces igual no
            repite la bitácora).

        Raises:
            CaseNotFoundError: Si el caso no existe o la persona no es miembro.
            CaseForbiddenError: Si su rol solo permite mirar.
            CaseClosedError: Si el caso está cerrado o archivado.
            RelationshipValidationError: Si el estado pedido es «sugerido».
            RelationshipNotFoundError: Si no hay un vínculo con esa llave entre
                entidades confirmadas del caso.
        """
        if status is ReviewStatus.SUGGESTED:
            raise RelationshipValidationError("Un vínculo se confirma o se descarta.", {})
        require_edit(await case_for(self._cases, case_id, actor))
        view = await _existing(self._relationships, case_id, key)
        if view.review_status is status:
            return view, False
        await self._relationships.save(case_id, *_review_write(view, status, actor))
        return await _existing(self._relationships, case_id, key), True


class ReviewRelationships:
    """Confirma o descarta varios vínculos a la vez (F12, ADR-0107)."""

    def __init__(
        self, cases: CaseRepositoryPort, relationships: RelationshipRepositoryPort
    ) -> None:
        """Recibe los repositorios.

        Args:
            cases: Casos (para los permisos).
            relationships: Vínculos.
        """
        self._cases = cases
        self._relationships = relationships

    async def execute(
        self,
        case_id: UUID,
        status: ReviewStatus,
        keys: Sequence[RelationshipKey],
        actor: Actor,
    ) -> BulkReviewResult:
        """Revisa todos o ninguno, con las mismas reglas que uno por uno.

        Los vínculos se calculan una sola vez para toda la petición. Los que
        ya estaban así no se tocan ni repiten la bitácora.

        Args:
            case_id: Caso.
            status: Confirmar o descartar.
            keys: Entidades y tipo de cada vínculo, como los devolvió la lista
                (en los simétricos se acepta cualquier orden).
            actor: Quién decide.

        Returns:
            Cuántos cambiaron y cuántos ya estaban así.

        Raises:
            BulkReviewError: Si viene vacía, con repetidos, con demasiados o
                pide regresar a «sugerido».
            InvalidRequestError: Si algún vínculo une a una entidad consigo misma.
            CaseNotFoundError: Si el caso no existe o la persona no es miembro.
            CaseForbiddenError: Si su rol solo permite mirar.
            CaseClosedError: Si el caso está cerrado o archivado.
            RelationshipNotFoundError: Si alguno ya no existe entre entidades
                confirmadas del caso.
        """
        wanted = [
            RelationshipKey(*ordered_pair(k.type, k.entity_a, k.entity_b), k.type) for k in keys
        ]
        check_bulk_review(status, wanted)
        require_edit(await case_for(self._cases, case_id, actor))
        views = {view.key: view for view in await self._relationships.list_case(case_id)}
        missing = [key for key in wanted if key not in views]
        if missing:
            raise RelationshipNotFoundError(
                "Alguno de los vínculos elegidos ya no está en el caso; vuelve a cargar la lista.",
                {"case_id": str(case_id), "missing": len(missing)},
            )
        items = [
            _review_write(views[key], status, actor, bulk=True)
            for key in wanted
            if views[key].review_status is not status
        ]
        if items:
            await self._relationships.save_many(case_id, items)
        return BulkReviewResult(changed=len(items), unchanged=len(wanted) - len(items))


def _review_write(
    view: RelationshipView, status: ReviewStatus, actor: Actor, *, bulk: bool = False
) -> tuple[RelationshipWrite, AuditEntry]:
    """Lo que se guarda al confirmar o descartar un vínculo, con su bitácora."""
    action = (
        InvestigationAction.RELATIONSHIP_CONFIRMED
        if status is ReviewStatus.CONFIRMED
        else InvestigationAction.RELATIONSHIP_DISCARDED
    )
    write = RelationshipWrite(
        relationship_id=view.relationship_id,
        key=view.key,
        custom_label=view.custom_label,
        origin=view.origin,
        confidence=view.confidence,
        review_status=status,
        reviewer=actor.user_id,
        notes=None,
    )
    payload: dict[str, object] = {**_payload(view), "before": view.review_status.value}
    if bulk:
        # Para distinguir en la bitácora lo que se decidió en bloque (ADR-0107).
        payload["bulk"] = True
    return write, AuditEntry(actor, action, payload)


class CreateRelationship:
    """El analista dibuja un vínculo entre dos entidades confirmadas (D7)."""

    def __init__(
        self,
        cases: CaseRepositoryPort,
        entities: EntityRepositoryPort,
        relationships: RelationshipRepositoryPort,
    ) -> None:
        """Recibe los repositorios.

        Args:
            cases: Casos (para los permisos).
            entities: Entidades (para validar las dos puntas).
            relationships: Vínculos.
        """
        self._cases = cases
        self._entities = entities
        self._relationships = relationships

    async def execute(
        self, case_id: UUID, data: RelationshipInput, actor: Actor
    ) -> tuple[RelationshipView, bool]:
        """Crea el vínculo confirmado con la firma de quien lo dibuja.

        Si ya existía con las mismas entidades y tipo (por ejemplo, sugerido por
        coocurrencia), se confirma ese en lugar de duplicarlo.

        Args:
            case_id: Caso.
            data: Entidades, tipo, etiqueta propia y nota.
            actor: Quién lo dibuja.

        Returns:
            El vínculo y si se creó o confirmó ahora (``False`` si ya estaba
            confirmado igual).

        Raises:
            CaseNotFoundError: Si el caso no existe o la persona no es miembro.
            CaseForbiddenError: Si su rol solo permite mirar.
            CaseClosedError: Si el caso está cerrado o archivado.
            RelationshipValidationError: Si el tipo, la etiqueta o la nota no
                son válidos, o alguna entidad no está confirmada en el caso.
            InvalidRequestError: Si las dos son la misma entidad.
        """
        kind, label, notes = manual_relationship(data.type, data.custom_label, data.notes)
        require_edit(await case_for(self._cases, case_id, actor))
        first, second = ordered_pair(kind, data.entity_a, data.entity_b)
        for entity_id in (first, second):
            await _confirmed(self._entities, case_id, entity_id)
        key = RelationshipKey(first, second, kind)
        existing = find(await self._relationships.list_case(case_id), key)
        if (
            existing is not None
            and existing.review_status is ReviewStatus.CONFIRMED
            and existing.custom_label == label
        ):
            return existing, False
        # La base admite un solo vínculo por par y tipo: un «otro» con una
        # etiqueta nueva reemplaza la etiqueta del que ya estaba.
        write = RelationshipWrite(
            relationship_id=existing.relationship_id if existing else None,
            key=key,
            custom_label=label,
            origin=existing.origin if existing else Origin.HUMAN,
            confidence=existing.confidence if existing else HUMAN_RELATIONSHIP_CONFIDENCE,
            review_status=ReviewStatus.CONFIRMED,
            reviewer=actor.user_id,
            notes=notes,
        )
        action = (
            InvestigationAction.RELATIONSHIP_CONFIRMED
            if existing
            else InvestigationAction.RELATIONSHIP_CREATED
        )
        audit = AuditEntry(
            actor,
            action,
            {
                "entity_a": first,
                "entity_b": second,
                "type": kind.value,
                "custom_label": label,
                "notes": notes,
                "origin": write.origin.value,
            },
        )
        await self._relationships.save(case_id, write, audit)
        return await _existing(self._relationships, case_id, key), True


async def _existing(
    relationships: RelationshipRepositoryPort, case_id: UUID, key: RelationshipKey
) -> RelationshipView:
    view = find(await relationships.list_case(case_id), key)
    if view is None:
        raise RelationshipNotFoundError(
            "No existe ese vínculo entre entidades confirmadas del caso.",
            {
                "case_id": str(case_id),
                "entity_a": key.entity_a,
                "entity_b": key.entity_b,
                "type": key.type.value,
            },
        )
    return view


async def _confirmed(entities: EntityRepositoryPort, case_id: UUID, entity_id: int) -> CaseEntity:
    entity = await entities.get_entity(case_id, entity_id)
    if entity is None or entity.review_status is not ReviewStatus.CONFIRMED:
        raise RelationshipValidationError(
            "Solo se vinculan entidades confirmadas del caso.", {"entity_id": entity_id}
        )
    return entity
