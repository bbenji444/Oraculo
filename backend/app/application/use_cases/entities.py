"""Casos de uso de las entidades de un caso (Fase 9.4, historia H9.2; ADR-0103).

Cuando una noticia entra a un caso, la IA la lee y propone personas,
organizaciones, lugares y vehículos. El analista confirma lo que sirve y
descarta el ruido; solo lo confirmado llegará al muro (9.6).

- ``QueueExtraction`` manda notas al worker (al agregarlas, y con
  "Analizar pendientes").
- ``ExtractCaseArticle`` (en el worker) lee una nota: reutiliza la lectura
  guardada si existe (sin pagar) o llama a la IA, revisa lo propuesto contra
  el texto (``review_proposals``) y lo convierte en sugerencias del caso.
- ``ListCaseEntities``, ``ConfirmEntity`` y ``DiscardEntity`` son lo que hace el
  analista, con los permisos de la 9.3 (``case_for`` y ``require_edit``).

Reglas que se cumplen aquí:

- Todo lo propuesto nace sugerido; nada se confirma ni se junta solo con
  algo ya revisado (ADR-0104).
- Confirmar a una persona exige su estatus legal, que nunca es "culpable"
  (ADR-0105).
- Cada lectura (correcta o fallida) va a la bitácora con su costo, y cada
  revisión con quién y qué cambió (CLAUDE.md §8).

No hace: no sabe de HTTP, SQL ni Celery; no fusiona entidades (9.5).
"""

from collections.abc import Sequence
from dataclasses import dataclass
from uuid import UUID

from app.application.audit import Actor, AuditEntry
from app.application.ports.cases import CaseRepositoryPort
from app.application.ports.entities import (
    CaseAnalysis,
    CaseEntity,
    EntityQueuePort,
    EntityRepositoryPort,
    FailedExtraction,
    Materialized,
    StoredExtraction,
)
from app.application.ports.llm import (
    EntityExtractionError,
    EntityExtractionRequest,
    EntityExtractorPort,
)
from app.application.use_cases.cases import case_for, require_edit
from app.application.use_cases.reports import LLMPrices
from app.domain.enrichment import LLMUsage
from app.domain.entity_extraction import (
    CASE_EXTRACTION_MAX_ARTICLES,
    CaseArticleEntitiesStatus,
    analyzed_text,
    confirmed_legal_status,
    estimated_extraction_usage,
    review_proposals,
)
from app.domain.errors import EntityNotFoundError, ProviderError
from app.domain.investigation import InvestigationAction, LegalStatus, ReviewStatus

NO_USAGE = LLMUsage(0, 0)
# El costo se guarda con 6 decimales (numeric(12, 6) en la migración 0020).
COST_DECIMALS = 6


def _cost(usage: LLMUsage, prices: LLMPrices) -> float:
    return round(usage.cost_usd(prices.input_per_million, prices.output_per_million), COST_DECIMALS)


class QueueExtraction:
    """Manda notas de un caso al worker para que la IA las lea."""

    def __init__(self, entities: EntityRepositoryPort, queue: EntityQueuePort) -> None:
        """Recibe el repositorio y la cola.

        Args:
            entities: Entidades y estado de análisis de los casos.
            queue: Cola del worker.
        """
        self._entities = entities
        self._queue = queue

    async def run(self, case_id: UUID, article_ids: Sequence[int], actor: Actor) -> int:
        """Marca las notas ``queued`` y las encola.

        Args:
            case_id: Caso.
            article_ids: Notas.
            actor: Quién lo pide (queda en la bitácora de cada lectura).

        Returns:
            Cuántas se encolaron.
        """
        if not article_ids:
            return 0
        # Primero el estado: si el worker termina antes de que se escriba,
        # no se debe pisar un "done" con "queued".
        await self._entities.set_status(case_id, article_ids, CaseArticleEntitiesStatus.QUEUED)
        for article_id in article_ids:
            self._queue.enqueue(case_id, article_id, actor.user_id)
        return len(article_ids)


@dataclass(frozen=True, slots=True)
class ExtractionOutcome:
    """Qué pasó con una nota del caso (para el worker y ``make extraer-entidades``).

    Attributes:
        article_id: Nota.
        status: ``done``, ``failed`` o ``skipped``.
        reused: Si se reutilizó una lectura guardada (sin pagar).
        extraction: La lectura revisada, si la hubo.
        cost_usd: Lo que pagó este caso por la nota.
        usage: Tokens de esta vez.
        materialized: Cómo quedaron las sugerencias.
        error: Qué falló, si falló.
    """

    article_id: int
    status: CaseArticleEntitiesStatus
    reused: bool = False
    extraction: StoredExtraction | None = None
    cost_usd: float = 0.0
    usage: LLMUsage = NO_USAGE
    materialized: Materialized | None = None
    error: str | None = None


class ExtractCaseArticle:
    """Lee una nota del caso con la IA y deja sus entidades como sugerencias."""

    def __init__(
        self,
        entities: EntityRepositoryPort,
        extractor: EntityExtractorPort,
        prices: LLMPrices,
        max_articles: int = CASE_EXTRACTION_MAX_ARTICLES,
    ) -> None:
        """Recibe las piezas.

        Args:
            entities: Entidades y estado de análisis de los casos.
            extractor: La IA.
            prices: Precios de esa IA (para guardar el costo).
            max_articles: Tope de notas leídas por caso (D2).
        """
        self._entities = entities
        self._extractor = extractor
        self._prices = prices
        self._max_articles = max_articles

    async def execute(
        self, case_id: UUID, article_id: int, actor: Actor
    ) -> ExtractionOutcome | None:
        """Lee la nota (o reutiliza su lectura) y la convierte en sugerencias del caso.

        Args:
            case_id: Caso.
            article_id: Nota.
            actor: Quién lo pidió (va en la bitácora).

        Returns:
            Qué pasó, o ``None`` si no había nada que hacer (la nota ya no está
            en el caso o ya se había leído).
        """
        source = await self._entities.article_source(case_id, article_id)
        if source is None or source.status is CaseArticleEntitiesStatus.DONE:
            return None
        if await self._entities.done_count(case_id) >= self._max_articles:
            await self._entities.set_status(
                case_id, [article_id], CaseArticleEntitiesStatus.SKIPPED
            )
            return ExtractionOutcome(article_id, CaseArticleEntitiesStatus.SKIPPED)

        version = self._extractor.entities_prompt_version
        stored = await self._entities.get_extraction(article_id, version)
        reused = stored is not None
        usage = NO_USAGE
        if stored is None:
            text = analyzed_text(
                source.title, source.stored_body, source.snippet, full_text=source.full_text
            )
            try:
                result = await self._extractor.extract_entities(
                    EntityExtractionRequest(text.title, text.body, source.published_at)
                )
            except (EntityExtractionError, ProviderError) as error:
                spent = error.usage if isinstance(error, EntityExtractionError) else NO_USAGE
                failure = FailedExtraction(
                    article_id,
                    version,
                    self._extractor.model,
                    text.source,
                    spent,
                    _cost(spent, self._prices),
                    str(error),
                )
                await self._entities.save_failure(case_id, failure, self._audit(actor, failure))
                return ExtractionOutcome(
                    article_id,
                    CaseArticleEntitiesStatus.FAILED,
                    cost_usd=failure.cost_usd,
                    usage=spent,
                    error=failure.error,
                )
            usage = result.usage
            stored = StoredExtraction(
                article_id,
                result.prompt_version,
                result.model,
                text.source,
                review_proposals(result.proposals, text),
                usage,
                _cost(usage, self._prices),
            )
            await self._entities.save_extraction(stored)

        cost = 0.0 if reused else stored.cost_usd
        materialized = await self._entities.materialize(
            case_id, stored, cost, self._audit(actor, stored, reused=reused, cost=cost)
        )
        if materialized is None:
            # La quitaron del caso mientras la IA la leía: la lectura queda
            # guardada para cuando vuelva, sin costo extra.
            return None
        return ExtractionOutcome(
            article_id,
            CaseArticleEntitiesStatus.DONE,
            reused=reused,
            extraction=stored,
            cost_usd=cost,
            usage=usage,
            materialized=materialized,
        )

    def _audit(
        self,
        actor: Actor,
        extraction: StoredExtraction | FailedExtraction,
        *,
        reused: bool = False,
        cost: float | None = None,
    ) -> AuditEntry:
        payload: dict[str, object] = {
            "article_id": extraction.article_id,
            "model": extraction.model,
            "prompt_version": extraction.prompt_version,
            "source": extraction.source.value,
            "tokens_in": 0 if reused else extraction.usage.tokens_in,
            "tokens_out": 0 if reused else extraction.usage.tokens_out,
            "cost_usd": extraction.cost_usd if cost is None else cost,
            "reused": reused,
        }
        if isinstance(extraction, FailedExtraction):
            payload |= {"status": "failed", "error": extraction.error}
        else:
            payload |= {
                "status": "ok",
                "proposals": len(extraction.reviewed.proposals),
                "rejected": len(extraction.reviewed.rejected),
            }
        return AuditEntry(actor, InvestigationAction.CASE_ENTITIES_EXTRACTED, payload)


@dataclass(frozen=True, slots=True)
class PendingRequest:
    """Resultado de "Analizar pendientes".

    Attributes:
        queued: Notas que se mandaron al worker.
        estimated_cost_usd: Lo que se calcula que costarán (antes de gastar).
    """

    queued: int
    estimated_cost_usd: float


def estimate_cost(articles: int, prices: LLMPrices | None) -> float:
    """Costo estimado de leer cierta cantidad de notas, antes de gastar.

    Args:
        articles: Notas.
        prices: Precios de la IA configurada, o ``None`` si no hay.

    Returns:
        Dólares estimados (0 sin precios).
    """
    if prices is None or articles == 0:
        return 0.0
    return _cost(estimated_extraction_usage(articles), prices)


class AnalyzePending:
    """Manda al worker las notas del caso que faltan por leer ("Analizar pendientes")."""

    def __init__(
        self,
        cases: CaseRepositoryPort,
        entities: EntityRepositoryPort,
        queuer: QueueExtraction,
        prices: LLMPrices | None,
        max_articles: int = CASE_EXTRACTION_MAX_ARTICLES,
    ) -> None:
        """Recibe las piezas.

        Args:
            cases: Casos (para los permisos).
            entities: Entidades y estado de análisis.
            queuer: Quien encola.
            prices: Precios de la IA, para estimar.
            max_articles: Tope de notas leídas por caso (D2).
        """
        self._cases = cases
        self._entities = entities
        self._queuer = queuer
        self._prices = prices
        self._max_articles = max_articles

    async def execute(self, case_id: UUID, actor: Actor) -> PendingRequest:
        """Encola las notas pendientes o fallidas, sin pasar del tope del caso.

        Args:
            case_id: Caso.
            actor: Quién lo pide.

        Returns:
            Cuántas se encolaron y su costo estimado.

        Raises:
            CaseNotFoundError: Si el caso no existe o la persona no es miembro.
            CaseForbiddenError: Si su rol solo permite mirar.
            CaseClosedError: Si el caso está cerrado o archivado.
        """
        require_edit(await case_for(self._cases, case_id, actor))
        room = max(self._max_articles - await self._entities.done_count(case_id), 0)
        article_ids = await self._entities.to_analyze(case_id, room) if room else []
        queued = await self._queuer.run(case_id, article_ids, actor)
        return PendingRequest(queued, estimate_cost(queued, self._prices))


@dataclass(frozen=True, slots=True)
class CaseEntities:
    """Lo que muestra la sección Entidades de un caso.

    Attributes:
        analysis: En qué va la lectura de sus notas y cuánto costó.
        counts: Cuántas entidades hay en cada estado.
        items: Las del estado pedido, las de más menciones primero.
        estimated_pending_cost_usd: Lo que costaría leer las que faltan.
    """

    analysis: CaseAnalysis
    counts: dict[ReviewStatus, int]
    items: tuple[CaseEntity, ...]
    estimated_pending_cost_usd: float


class ListCaseEntities:
    """Entidades de un caso en un estado de revisión, con su evidencia."""

    def __init__(
        self,
        cases: CaseRepositoryPort,
        entities: EntityRepositoryPort,
        prices: LLMPrices | None,
    ) -> None:
        """Recibe las piezas.

        Args:
            cases: Casos (para los permisos).
            entities: Entidades.
            prices: Precios de la IA, para estimar lo pendiente.
        """
        self._cases = cases
        self._entities = entities
        self._prices = prices

    async def execute(self, case_id: UUID, actor: Actor, status: ReviewStatus) -> CaseEntities:
        """Lista las entidades del caso en ese estado.

        Mirarlas no va a la bitácora por separado: abrir el caso ya quedó
        como ``case.viewed``.

        Args:
            case_id: Caso.
            actor: Quién pregunta (cualquier miembro, también un lector).
            status: Sugeridas, confirmadas o descartadas.

        Returns:
            Avance, conteos y entidades.

        Raises:
            CaseNotFoundError: Si el caso no existe o la persona no es miembro.
        """
        await case_for(self._cases, case_id, actor)
        analysis = await self._entities.analysis(case_id)
        items = await self._entities.list_entities(case_id, status)
        ordered = sorted(items, key=lambda e: (-len(e.mentions), e.label.casefold(), e.entity_id))
        return CaseEntities(
            analysis=analysis,
            counts=await self._entities.review_counts(case_id),
            items=tuple(ordered),
            estimated_pending_cost_usd=estimate_cost(
                analysis.pending + analysis.failed, self._prices
            ),
        )


def _snapshot(entity: CaseEntity) -> dict[str, object]:
    return {
        "review_status": entity.review_status.value,
        "legal_status": entity.legal_status.value if entity.legal_status else None,
    }


class ConfirmEntity:
    """Confirma una entidad sugerida (o corrige el estatus de una confirmada)."""

    def __init__(self, cases: CaseRepositoryPort, entities: EntityRepositoryPort) -> None:
        """Recibe los repositorios.

        Args:
            cases: Casos (para los permisos).
            entities: Entidades.
        """
        self._cases = cases
        self._entities = entities

    async def execute(
        self, case_id: UUID, entity_id: int, legal_status: str | None, actor: Actor
    ) -> tuple[CaseEntity, bool]:
        """Confirma con firma y bitácora.

        Args:
            case_id: Caso donde se revisa.
            entity_id: Entidad.
            legal_status: Estatus legal elegido (obligatorio en personas,
                vacío en lo demás).
            actor: Quién confirma.

        Returns:
            La entidad como quedó y si cambió (confirmar dos veces igual no
            repite la bitácora).

        Raises:
            CaseNotFoundError: Si el caso no existe o la persona no es miembro.
            CaseForbiddenError: Si su rol solo permite mirar.
            CaseClosedError: Si el caso está cerrado o archivado.
            EntityNotFoundError: Si la entidad no es de ese caso.
            EntityReviewError: Si falta el estatus legal de una persona o sobra en
                lo demás.
        """
        entity = await _entity_to_review(self._cases, self._entities, case_id, entity_id, actor)
        legal = confirmed_legal_status(entity.type, legal_status)
        if entity.review_status is ReviewStatus.CONFIRMED and entity.legal_status == legal:
            return entity, False
        return await _review(
            self._entities,
            case_id=case_id,
            entity=entity,
            status=ReviewStatus.CONFIRMED,
            legal_status=legal,
            actor=actor,
        ), True


class DiscardEntity:
    """Descarta una entidad: deja de proponerse, sin borrarla (queda su evidencia)."""

    def __init__(self, cases: CaseRepositoryPort, entities: EntityRepositoryPort) -> None:
        """Recibe los repositorios.

        Args:
            cases: Casos (para los permisos).
            entities: Entidades.
        """
        self._cases = cases
        self._entities = entities

    async def execute(self, case_id: UUID, entity_id: int, actor: Actor) -> tuple[CaseEntity, bool]:
        """Descarta con firma y bitácora.

        Args:
            case_id: Caso donde se revisa.
            entity_id: Entidad.
            actor: Quién descarta.

        Returns:
            La entidad como quedó y si cambió.

        Raises:
            CaseNotFoundError: Si el caso no existe o la persona no es miembro.
            CaseForbiddenError: Si su rol solo permite mirar.
            CaseClosedError: Si el caso está cerrado o archivado.
            EntityNotFoundError: Si la entidad no es de ese caso.
        """
        entity = await _entity_to_review(self._cases, self._entities, case_id, entity_id, actor)
        if entity.review_status is ReviewStatus.DISCARDED:
            return entity, False
        return await _review(
            self._entities,
            case_id=case_id,
            entity=entity,
            status=ReviewStatus.DISCARDED,
            legal_status=entity.legal_status,
            actor=actor,
        ), True


async def _entity_to_review(
    cases: CaseRepositoryPort,
    entities: EntityRepositoryPort,
    case_id: UUID,
    entity_id: int,
    actor: Actor,
) -> CaseEntity:
    require_edit(await case_for(cases, case_id, actor))
    entity = await entities.get_entity(case_id, entity_id)
    if entity is None:
        raise EntityNotFoundError(
            "No existe esa entidad en el caso.", {"case_id": str(case_id), "entity_id": entity_id}
        )
    return entity


async def _review(  # noqa: PLR0913 — la revisión firmada necesita todos sus datos
    entities: EntityRepositoryPort,
    *,
    case_id: UUID,
    entity: CaseEntity,
    status: ReviewStatus,
    legal_status: LegalStatus | None,
    actor: Actor,
) -> CaseEntity:
    action = (
        InvestigationAction.ENTITY_CONFIRMED
        if status is ReviewStatus.CONFIRMED
        else InvestigationAction.ENTITY_DISCARDED
    )
    suggested = entity.suggested_legal_status
    audit = AuditEntry(
        actor,
        action,
        {
            "entity_id": entity.entity_id,
            "type": entity.type.value,
            "label": entity.label,
            "before": _snapshot(entity),
            "after": {
                "review_status": status.value,
                "legal_status": legal_status.value if legal_status else None,
            },
            "suggested_legal_status": suggested.value if suggested else None,
            "mentions": len(entity.mentions),
        },
    )
    return await entities.review(
        case_id,
        entity.entity_id,
        status=status,
        legal_status=legal_status,
        reviewer=actor.user_id,
        audit=audit,
    )
