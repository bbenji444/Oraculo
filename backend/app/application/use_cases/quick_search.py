"""Búsqueda rápida: buscar «como en Google» sin guardar un concepto (ADR-0110).

Benji (17/11/2026): «que en vez de tener un concepto guardado, sea como
búsqueda rápida y lo pongas así como en el buscador de Google».

``StartQuickSearch``:

1. le pide a la IA las frases de lo que escribió el analista
   (``SuggestConceptTerms``, que valida el texto y deja la propuesta en la
   bitácora);
2. crea un concepto **oculto** «como en Google» con ese texto como lo que se
   juzga y las frases de la IA. No sale en la lista de conceptos ni ocupa su
   nombre;
3. lanza la búsqueda con ese concepto, la región y las fechas elegidas
   (``StartSearch``, con sus mismos topes y revisiones).

Se apoya en un concepto porque todo el pipeline (el juicio de la IA,
``search_concepts``, ``article_concepts``, el historial) se apoya en ellos.

``KeepQuickConcept`` lo vuelve un concepto normal («Guardar como concepto»).

Lo usan ``POST /api/v1/searches/quick`` y ``POST /api/v1/concepts/{id}/keep``.

No hace: no corre la búsqueda (eso lo hace el worker) ni sabe de HTTP.
"""

from dataclasses import dataclass

from app.application.audit import (
    CONCEPT_CREATED,
    CONCEPT_UPDATED,
    Actor,
    AuditEntry,
    concept_snapshot,
)
from app.application.ports.concepts import ConceptRepositoryPort
from app.application.use_cases.plan_search import SearchRequest
from app.application.use_cases.start_search import StartedSearch, StartSearch
from app.application.use_cases.suggest_terms import SuggestConceptTerms, TermProposal
from app.domain.concept import NAME_MAX_LENGTH, Concept, ConceptDraft, QueryMode
from app.domain.errors import ConceptNameTakenError, ConceptNotFoundError
from app.domain.queries import DateWindow, Provider

# Color de las búsquedas rápidas en el mapa: el cian de la consola de Oráculo
# (ADR-0108), para que no se confunda con los conceptos guardados.
QUICK_COLOR = "#00D2FF"


def quick_name(proposed: str, text: str) -> str:
    """Nombre del concepto oculto: el de la IA o, si no sirvió, el texto.

    Args:
        proposed: Nombre que propuso la IA (``""`` si no sirvió).
        text: Lo que escribió el analista.

    Returns:
        Un nombre de hasta ``NAME_MAX_LENGTH`` caracteres, cortado en un
        espacio para no partir palabras.

    Example:
        >>> quick_name("", "robo de autos con violencia en Jalisco")
        'robo de autos con violencia en Jalisco'
    """
    name = proposed.strip() or " ".join(text.split())
    if len(name) <= NAME_MAX_LENGTH:
        return name
    cut = name[:NAME_MAX_LENGTH]
    return cut.rsplit(" ", 1)[0] if " " in cut else cut


@dataclass(frozen=True, slots=True)
class QuickSearchRequest:
    """Lo que escribió el analista y dónde y cuándo buscar.

    Attributes:
        user_id: Quién busca.
        text: Lo que quiere encontrar, en sus palabras.
        region_id: Región.
        window: Rango de fechas.
        providers: Fuentes encendidas, o ``None`` para las de por defecto.
    """

    user_id: str
    text: str
    region_id: int
    window: DateWindow
    providers: tuple[Provider, ...] | None = None


@dataclass(frozen=True, slots=True)
class QuickSearchStarted:
    """Una búsqueda rápida recién lanzada.

    Attributes:
        concept: El concepto oculto que se creó.
        proposal: Lo que propuso la IA y cuánto costó.
        search: La búsqueda lanzada y su costo estimado.
    """

    concept: Concept
    proposal: TermProposal
    search: StartedSearch


class StartQuickSearch:
    """Caso de uso: de un texto libre a una búsqueda lanzada."""

    def __init__(
        self,
        suggester: SuggestConceptTerms,
        concepts: ConceptRepositoryPort,
        starter: StartSearch,
    ) -> None:
        """Recibe las piezas que ya existen para cada paso.

        Args:
            suggester: La IA que propone las frases.
            concepts: Repositorio de conceptos.
            starter: Lanzador de búsquedas.
        """
        self._suggester = suggester
        self._concepts = concepts
        self._starter = starter

    async def execute(self, request: QuickSearchRequest, actor: Actor) -> QuickSearchStarted:
        """Propone las frases, crea el concepto oculto y lanza la búsqueda.

        Args:
            request: Texto, región, fechas y fuentes.
            actor: Quién busca (para la bitácora).

        Returns:
            El concepto, la propuesta y la búsqueda lanzada.

        Raises:
            ConceptValidationError: Si el texto es muy corto o muy largo.
            TermSuggestionFailedError: Si la IA no dio frases.
            EmptySuggestionError: Si no quedó ninguna frase que se pueda buscar.
            LLMNotConfiguredError, CreditLimitReachedError, QueryBudgetExceededError:
                Los mismos rechazos de ``StartSearch``; el concepto oculto
                queda creado pero no estorba.
        """
        proposal = await self._suggester.execute(request.text, actor)
        draft = ConceptDraft.validated(
            name=quick_name(proposal.terms.name, request.text),
            description=request.text,
            keywords=proposal.terms.phrases,
            exclude_terms=proposal.terms.exclude_terms,
            color=QUICK_COLOR,
            query_mode=QueryMode.OPEN,
        )
        audit = AuditEntry(
            actor, CONCEPT_CREATED, {"after": concept_snapshot(draft), "busqueda_rapida": True}
        )
        concept = await self._concepts.create(draft, actor.user_id, audit, quick=True)
        search = await self._starter.execute(
            SearchRequest(
                request.user_id,
                (concept.id,),
                request.region_id,
                request.window,
                request.providers,
            )
        )
        return QuickSearchStarted(concept, proposal, search)


class KeepQuickConcept:
    """Caso de uso: «Guardar como concepto» una búsqueda rápida."""

    def __init__(self, concepts: ConceptRepositoryPort) -> None:
        """Recibe el repositorio.

        Args:
            concepts: Repositorio de conceptos.
        """
        self._concepts = concepts

    async def execute(self, concept_id: int, actor: Actor) -> Concept:
        """Lo vuelve visible en la lista de conceptos.

        Args:
            concept_id: El concepto oculto.
            actor: Quién lo guarda.

        Returns:
            El concepto ya guardado.

        Raises:
            ConceptNotFoundError: Si no existe o ya era un concepto normal.
            ConceptNameTakenError: Si ya hay un concepto con ese nombre; se
                renombra desde Conceptos o se edita antes.
        """
        concept = await self._concepts.get(concept_id)
        if concept is None or not concept.is_quick:
            raise ConceptNotFoundError("No hay una búsqueda rápida con ese id.", {"id": concept_id})
        if await self._concepts.name_taken(concept.data.name_norm, concept_id):
            raise ConceptNameTakenError(
                f'Ya existe un concepto llamado "{concept.data.name}". '
                "Cambia el nombre de la búsqueda rápida antes de guardarla.",
                {"name": concept.data.name},
            )
        snapshot = concept_snapshot(concept.data)
        audit = AuditEntry(
            actor,
            CONCEPT_UPDATED,
            {"before": snapshot | {"is_quick": True}, "after": snapshot | {"is_quick": False}},
        )
        return await self._concepts.keep(concept_id, audit)
