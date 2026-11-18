"""Búsqueda rápida: buscar «como en Google» sin guardar un concepto (ADR-0110).

Benji (17/11/2026): «que en vez de tener un concepto guardado, sea como
búsqueda rápida y lo pongas así como en el buscador de Google».

``StartQuickSearch``:

1. le pide a la IA las frases de lo que escribió el analista, el lugar que
   nombra («en Jalisco») y sus nombres propios («Eternal»)
   (``SuggestConceptTerms``, que valida el texto y deja la propuesta en la
   bitácora);
2. si nombra un lugar que está en el catálogo, se busca ahí; si dice «en
   todo el mundo» o algo así, en «Mundo» (ADR-0112); si no, en la región que
   eligió en la consulta;
3. arma el **literal**: el texto tal como lo escribió, sin el lugar ni «en
   todo el mundo» (``literal_phrase``, ADR-0113). Benji buscó «Hacker
   Eternal» y la IA lo volvió «Hackeo Eternal»: 0 notas. El literal es la
   primera frase y el nombre del concepto; la IA ya no lo renombra;
4. crea un concepto **oculto** «como en Google» con el texto como lo que se
   juzga, el literal y las frases de la IA, y los nombres propios como
   términos obligatorios. No sale en la lista de conceptos ni ocupa su
   nombre;
5. lanza la búsqueda con ese concepto, la región y las fechas elegidas
   (``StartSearch``, con sus mismos topes y revisiones). Si el analista no
   eligió fuentes, van las de ``QUICK_DEFAULT_SOURCES``: las de noticias
   gratis más Google web, que trae redes sociales (ADR-0115). Si Google web
   no alcanza los créditos del mes, la búsqueda no falla: se lanza sin él y
   lo avisa (``NO_WEB_CREDITS_NOTICE``).

Se apoya en un concepto porque todo el pipeline (el juicio de la IA,
``search_concepts``, ``article_concepts``, el historial) se apoya en ellos.

``KeepQuickConcept`` lo vuelve un concepto normal («Guardar como concepto»).

Lo usan ``POST /api/v1/searches/quick`` y ``POST /api/v1/concepts/{id}/keep``.

No hace: no corre la búsqueda (eso lo hace el worker) ni sabe de HTTP.
"""

from collections.abc import Sequence
from dataclasses import dataclass, replace

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
from app.domain.budget import NO_WEB_CREDITS_NOTICE
from app.domain.concept import NAME_MAX_LENGTH, Concept, ConceptDraft, QueryMode
from app.domain.errors import (
    ConceptNameTakenError,
    ConceptNotFoundError,
    CreditLimitReachedError,
)
from app.domain.names import normalize_name
from app.domain.queries import DateWindow, Provider, place_for
from app.domain.region import WORLD_CODE, Region, RegionLevel
from app.domain.term_suggestions import (
    LITERAL_MAX_WORDS,
    EmptySuggestionError,
    SuggestedTerms,
    clean_suggestion,
    literal_fits,
    literal_phrase,
    names_whole_world,
    with_literal,
    without_places,
)

# Color de las búsquedas rápidas en el mapa: el cian de la consola de Oráculo
# (ADR-0108), para que no se confunda con los conceptos guardados.
QUICK_COLOR = "#00D2FF"

# Cuántas regiones del catálogo se revisan al buscar el lugar del texto: hay
# nombres repetidos en varios estados ("San Pedro"), y con 10 caben el
# municipio y las localidades homónimas más comunes.
PLACE_CANDIDATES = 10

# Fuentes de la búsqueda rápida si el analista no elige (ADR-0115): las de
# noticias gratis más Google web, que trae Facebook, X, YouTube y sitios que
# no son de noticias, como el buscador. Las manuales siguen con
# ``MANUAL_DEFAULT_SOURCES``. ``QUICK_DEFAULT_SOURCES`` en ``.env`` la cambia.
QUICK_DEFAULT_SOURCES: tuple[Provider, ...] = (
    Provider.GOOGLE_NEWS_RSS,
    Provider.LOCAL_INDEX,
    Provider.SEARCHAPI_WEB,
)


def without_web(request: SearchRequest) -> SearchRequest | None:
    """La misma búsqueda sin Google web, para cuando no alcanzan los créditos.

    Args:
        request: La búsqueda que se quiso lanzar.

    Returns:
        La búsqueda sin ``searchapi_web`` en sus fuentes (las elegidas o, si
        no eligió, las de por defecto), o ``None`` si no lo llevaba o si sin
        él no queda ninguna fuente: entonces no hay a qué volver.

    Example:
        >>> without_web(SearchRequest(..., default_sources=QUICK_DEFAULT_SOURCES))
        SearchRequest(..., default_sources=(GOOGLE_NEWS_RSS, LOCAL_INDEX))
    """
    chosen = request.providers if request.providers is not None else request.default_sources
    if chosen is None or Provider.SEARCHAPI_WEB not in chosen:
        return None
    rest = tuple(p for p in chosen if p is not Provider.SEARCHAPI_WEB)
    if not rest:
        return None
    if request.providers is not None:
        return replace(request, providers=rest)
    return replace(request, default_sources=rest)


def quick_name(literal: str | None, text: str) -> str:
    """Nombre del concepto oculto: el literal del analista o, si no hay, su texto.

    Desde ADR-0113 la IA ya no lo pone: «hacker eternal» salía como «Hackeo
    Eternal» en el Centro de mando y en el historial, y Benji sentía que el
    sistema le cambiaba la búsqueda.

    Args:
        literal: El texto listo para buscarse (``literal_phrase``), o ``None``.
        text: Lo que escribió el analista.

    Returns:
        Un nombre de hasta ``NAME_MAX_LENGTH`` caracteres, cortado en un
        espacio para no partir palabras.

    Example:
        >>> quick_name("hacker eternal", "hacker eternal en todo el mundo")
        'hacker eternal'
        >>> quick_name(None, "robo de autos con violencia en Jalisco")
        'robo de autos con violencia en Jalisco'
    """
    name = (literal or "").strip() or " ".join(text.split())
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


async def place_names(regions: RegionRepositoryPort, place: Region) -> tuple[str, ...]:
    """Todos los nombres del lugar que reconoció la búsqueda rápida.

    Args:
        regions: Catálogo de regiones.
        place: La región resuelta.

    Returns:
        Su nombre, alias y términos de búsqueda, y los nombres de su estado
        y su país (``ancestors``): ninguno es un nombre propio del pedido
        (revisión del 18/11/2026, hallazgo 3).
    """
    names = [place.name, *place.aliases]
    facts = await regions.place_facts(place.id)
    if facts is not None:
        names.extend((facts.name, *facts.search_terms, *facts.state_search_terms))
        if facts.state_name:
            names.append(facts.state_name)
    names.extend(ref.name for ref in await regions.ancestors(place.id))
    return tuple(dict.fromkeys(names))


def entities_without_place(proposal: TermProposal, names: Sequence[str]) -> SuggestedTerms:
    """La propuesta sin las entidades que resultaron ser el lugar del catálogo.

    ``SuggestConceptTerms`` ya quitó el lugar que dio la IA; aquí se quitan
    sus otros nombres («CDMX» cuando la IA dijo «Ciudad de México»). Si
    alguna sobra, las frases se vuelven a limpiar con lo que respondió la
    IA: con la entidad equivocada se habrían tirado las que no la llevan.

    Args:
        proposal: Lo que propuso la IA ya limpio, con su respuesta original.
        names: Nombres del lugar (``place_names``).

    Returns:
        Las frases, exclusiones y entidades que quedan.
    """
    terms = proposal.terms
    entities = without_places(terms.entities, names)
    if entities == terms.entities or proposal.raw is None:
        return replace(terms, entities=entities)
    raw = proposal.raw
    return clean_suggestion(
        raw.name, raw.phrases, raw.exclude_terms, entities=entities, require_phrases=False
    )


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
        notice: Aviso para el analista si se buscó con menos fuentes
            (``NO_WEB_CREDITS_NOTICE``, ADR-0115); ``None`` si no hay.
    """

    concept: Concept
    proposal: TermProposal
    search: StartedSearch
    place_region: Region | None = None
    notice: str | None = None


class StartQuickSearch:
    """Caso de uso: de un texto libre a una búsqueda lanzada."""

    def __init__(
        self,
        suggester: SuggestConceptTerms,
        concepts: ConceptRepositoryPort,
        starter: StartSearch,
        regions: RegionRepositoryPort,
        default_sources: Sequence[Provider] = QUICK_DEFAULT_SOURCES,
    ) -> None:
        """Recibe las piezas que ya existen para cada paso.

        Args:
            suggester: La IA que propone las frases.
            concepts: Repositorio de conceptos.
            starter: Lanzador de búsquedas.
            regions: Catálogo, para el lugar que nombre el texto.
            default_sources: Fuentes si el analista no elige
                (``QUICK_DEFAULT_SOURCES`` del ``.env``). Las que no están
                configuradas se quedan fuera solas, como en la manual.
        """
        self._suggester = suggester
        self._concepts = concepts
        self._starter = starter
        self._regions = regions
        self._default_sources = tuple(default_sources)

    async def _launch(self, request: SearchRequest) -> tuple[StartedSearch, str | None]:
        """Lanza la búsqueda; si Google web no alcanza créditos, sin él.

        Benji (18/11/2026): a la cuenta de SearchApi le quedaban 47 créditos
        que no se renuevan. Cuando se acaben, la búsqueda rápida sigue con
        las fuentes de noticias en vez de responder «tope de créditos».
        «No alcanza» lo decide ``StartSearch`` con el saldo real de la cuenta
        (``GET /me``) y el tope mensual local (revisión del 18/11/2026).

        Args:
            request: La búsqueda con sus fuentes.

        Returns:
            La búsqueda lanzada y el aviso si se quitó Google web.

        Raises:
            CreditLimitReachedError: Si ni sin Google web cabe (el analista
                encendió también Google News de pago) o si Google web era la
                única fuente.
        """
        try:
            return await self._starter.execute(request), None
        except CreditLimitReachedError:
            fallback = without_web(request)
            if fallback is None:
                raise
        return await self._starter.execute(fallback), NO_WEB_CREDITS_NOTICE

    async def _fitting(
        self,
        literal: str | None,
        region_id: int,
        exclusions: Sequence[str],
        window: DateWindow,
    ) -> str | None:
        """El literal si cabe en una consulta de cada proveedor; si no, ``None``.

        Revisión del 18/11/2026 (hallazgo 7): el literal ya puede tener hasta
        ``LITERAL_MAX_WORDS`` palabras, y con el lugar y «when:7d» podría
        pasar del límite de Google y tirar la búsqueda entera
        (``QueryTooLongError``). Sin él, se busca con las frases de la IA.

        Args:
            literal: El texto del analista (``literal_phrase``), o ``None``.
            region_id: Región donde se va a buscar.
            exclusions: Exclusiones del concepto.
            window: Rango de fechas.

        Returns:
            El literal, o ``None`` si no hay o no cabe. Si la región no
            existe, el literal tal cual: ``StartSearch`` da su propio error.
        """
        if literal is None:
            return None
        facts = await self._regions.place_facts(region_id)
        if facts is None or literal_fits(literal, place_for(facts), exclusions, window):
            return literal
        return None

    async def execute(self, request: QuickSearchRequest, actor: Actor) -> QuickSearchStarted:
        """Propone las frases, crea el concepto oculto y lanza la búsqueda.

        Si el texto nombra un lugar del catálogo («en Jalisco»), se busca ahí
        aunque se haya elegido otro: lo escrito es lo más reciente que dijo
        el analista. Benji (17/11/2026): «robo de autos con violencia en
        Jalisco» buscaba en todo México.

        Lo escrito se busca tal cual (ADR-0113): el literal va primero, sin el
        lugar, y es el nombre del concepto. Las frases de la IA van después y
        solo las que llevan los nombres propios del texto.

        Args:
            request: Texto, región, fechas y fuentes.
            actor: Quién busca (para la bitácora).

        Returns:
            El concepto, la propuesta y la búsqueda lanzada.

        Raises:
            ConceptValidationError: Si el texto es muy corto o muy largo.
            TermSuggestionFailedError: Si la IA no dio frases.
            EmptySuggestionError: Si no hay literal ni frase de la IA que se
                pueda buscar.
            LLMNotConfiguredError, CreditLimitReachedError, QueryBudgetExceededError:
                Los mismos rechazos de ``StartSearch``; el concepto oculto
                queda creado pero no estorba. Por créditos solo falla si ni
                sin Google web cabe (``_launch``).
        """
        # Sin frases útiles de la IA todavía queda el literal, y basta un
        # nombre («Pemex», revisión del 18/11/2026).
        proposal = await self._suggester.execute(
            request.text, actor, require_phrases=False, quick=True
        )
        terms = proposal.terms
        place = await resolve_place(self._regions, proposal.place, proposal.place_state)
        if place is not None:
            terms = entities_without_place(proposal, await place_names(self._regions, place))
        literal = literal_phrase(
            request.text,
            proposal.place if place is not None else None,
            # El texto puede decir «CDMX» aunque la IA diga «Ciudad de México».
            aliases=(place.name, *place.aliases) if place is not None else (),
            entities=terms.entities,
        )
        literal = await self._fitting(
            literal,
            place.id if place is not None else request.region_id,
            terms.exclude_terms,
            request.window,
        )
        keywords, exclusions = with_literal(literal, terms.phrases, terms.exclude_terms)
        if not keywords:
            raise EmptySuggestionError(
                "No se puede buscar ese texto tal cual y la IA no propuso frases que se "
                "puedan buscar. Escríbelo con otras palabras, más corto."
            )
        draft = ConceptDraft.validated(
            name=quick_name(literal, request.text),
            description=request.text,
            keywords=keywords,
            exclude_terms=exclusions,
            color=QUICK_COLOR,
            query_mode=QueryMode.OPEN,
            required_terms=terms.entities,
            # El literal va completo aunque pase de 80 caracteres (ADR-0113).
            literal_max_words=LITERAL_MAX_WORDS if literal is not None else None,
        )
        audit = AuditEntry(
            actor, CONCEPT_CREATED, {"after": concept_snapshot(draft), "busqueda_rapida": True}
        )
        concept = await self._concepts.create(draft, actor.user_id, audit, quick=True)
        # Un lugar del catálogo gana: «robo de autos en Jalisco, de los más
        # altos en el mundo» es de Jalisco.
        if place is None and names_whole_world(request.text):
            place = await self._regions.get_by_code(WORLD_CODE)
        search, notice = await self._launch(
            SearchRequest(
                request.user_id,
                (concept.id,),
                place.id if place is not None else request.region_id,
                request.window,
                request.providers,
                default_sources=self._default_sources,
            )
        )
        return QuickSearchStarted(concept, proposal, search, place, notice)


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
