"""Búsqueda rápida: buscar «como en Google» sin guardar un concepto (ADR-0110).

Benji (17/11/2026): «que en vez de tener un concepto guardado, sea como
búsqueda rápida y lo pongas así como en el buscador de Google».

``StartQuickSearch``:

1. le pide a la IA las frases de lo que escribió el analista y el lugar que
   nombra («en Jalisco»), si nombra uno (``SuggestConceptTerms``, que valida
   el texto y deja la propuesta en la bitácora);
2. si nombra un lugar que está en el catálogo, se busca ahí; si no, en la
   región que eligió en la consulta;
3. crea un concepto **oculto** «como en Google» con ese texto como lo que se
   juzga y las frases de la IA. No sale en la lista de conceptos ni ocupa su
   nombre;
4. lanza la búsqueda con ese concepto, la región y las fechas elegidas
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
from app.application.ports.regions import RegionRepositoryPort
from app.application.use_cases.plan_search import SearchRequest
from app.application.use_cases.start_search import StartedSearch, StartSearch
from app.application.use_cases.suggest_terms import SuggestConceptTerms, TermProposal
from app.domain.concept import NAME_MAX_LENGTH, Concept, ConceptDraft, QueryMode
from app.domain.errors import ConceptNameTakenError, ConceptNotFoundError
from app.domain.names import normalize_name
from app.domain.queries import DateWindow, Provider
from app.domain.region import Region, RegionLevel

# Color de las búsquedas rápidas en el mapa: el cian de la consola de Oráculo
# (ADR-0108), para que no se confunda con los conceptos guardados.
QUICK_COLOR = "#00D2FF"

# Cuántas regiones del catálogo se revisan al buscar el lugar del texto: hay
# nombres repetidos en varios estados ("San Pedro"), y con 10 caben el
# municipio y las localidades homónimas más comunes.
PLACE_CANDIDATES = 10


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


def _named(region: Region, norm: str) -> bool:
    """Si la región se llama exactamente así (por nombre o alias)."""
    return region.name_norm == norm or norm in {normalize_name(a) for a in region.aliases}


async def resolve_place(
    regions: RegionRepositoryPort, place: str | None, state: str | None
) -> Region | None:
    """Busca en el catálogo el lugar que nombró el analista.

    Solo acepta nombres exactos (o alias): un parecido («Jaliscos») no basta,
    porque buscar en el lugar equivocado es peor que buscar en el elegido.
    Si hay varios con el mismo nombre, gana el que está en el estado que dio
    la IA; sin estado, el más general (el estado antes que una localidad).

    Args:
        regions: Catálogo de regiones.
        place: Lugar que nombró el analista («Guadalajara»), o ``None``.
        state: Estado de ese lugar («Jalisco»), o ``None``.

    Returns:
        La región, o ``None`` si no nombró lugar o no está en el catálogo.

    Example:
        >>> await resolve_place(regions, "Guadalajara", "Jalisco")
        Region(code="14039", name="Guadalajara", ...)
    """
    if not place:
        return None
    norm = normalize_name(place)
    found = [r for r in await regions.search(norm, PLACE_CANDIDATES) if _named(r, norm)]
    if not found:
        return None
    if state:
        state_norm = normalize_name(state)
        for candidate in found:
            chain = await regions.ancestors(candidate.id)
            if any(
                ref.level is RegionLevel.STATE and normalize_name(ref.name) == state_norm
                for ref in chain
            ):
                return candidate
    return found[0]


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
        place_region: La región que nombró el texto, si se buscó ahí; ``None``
            si se buscó en la región elegida.
    """

    concept: Concept
    proposal: TermProposal
    search: StartedSearch
    place_region: Region | None = None


class StartQuickSearch:
    """Caso de uso: de un texto libre a una búsqueda lanzada."""

    def __init__(
        self,
        suggester: SuggestConceptTerms,
        concepts: ConceptRepositoryPort,
        starter: StartSearch,
        regions: RegionRepositoryPort,
    ) -> None:
        """Recibe las piezas que ya existen para cada paso.

        Args:
            suggester: La IA que propone las frases.
            concepts: Repositorio de conceptos.
            starter: Lanzador de búsquedas.
            regions: Catálogo, para el lugar que nombre el texto.
        """
        self._suggester = suggester
        self._concepts = concepts
        self._starter = starter
        self._regions = regions

    async def execute(self, request: QuickSearchRequest, actor: Actor) -> QuickSearchStarted:
        """Propone las frases, crea el concepto oculto y lanza la búsqueda.

        Si el texto nombra un lugar del catálogo («en Jalisco»), se busca ahí
        aunque se haya elegido otro: lo escrito es lo más reciente que dijo
        el analista. Benji (17/11/2026): «robo de autos con violencia en
        Jalisco» buscaba en todo México.

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
        place = await resolve_place(self._regions, proposal.place, proposal.place_state)
        search = await self._starter.execute(
            SearchRequest(
                request.user_id,
                (concept.id,),
                place.id if place is not None else request.region_id,
                request.window,
                request.providers,
            )
        )
        return QuickSearchStarted(concept, proposal, search, place)


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
