"""Planear una búsqueda y estimar su costo antes de gastar (§9 paso 1; ADR-0015).

Lo usan ``POST /searches/estimate``, ``POST /searches`` y ``make buscar``,
para que la pantalla y la terminal den siempre los mismos números:

- las consultas que se harían, con los conceptos y la región guardados;
- los créditos de SearchApi (Google News y Google web, que comparten cuenta,
  ADR-0115), lo ya gastado en el mes y su tope, y el saldo real de la cuenta
  (``CreditBalancePort``, revisión del 18/11/2026): la cuenta de prueba tenía
  46 créditos que no se renuevan, menos que lo que dejaba el tope local;
- el costo máximo de la IA (``LLM_MAX_ARTICLES_PER_SEARCH`` notas con la
  tarifa del modelo elegido). Lo real suele ser menor: las notas ya
  procesadas no se pagan.

No hace: no crea la búsqueda ni consulta a nadie (``ExecuteQueries`` y
``RunSearch`` lo hacen después).
"""

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from app.application.clock import MEXICO_CITY
from app.application.ports.concepts import ConceptRepositoryPort
from app.application.ports.credit_balance import CreditBalancePort
from app.application.ports.llm import LLMInfo
from app.application.ports.provider_log import ProviderQueryLogPort
from app.application.ports.providers import NewsProviderPort
from app.application.ports.regions import RegionRepositoryPort
from app.application.ports.search_store import NewSearch, SearchConcept
from app.application.use_cases.run_search import plan_queries
from app.domain.budget import account_providers, month_start
from app.domain.enrichment import estimated_usage
from app.domain.errors import (
    ConceptNotFoundError,
    InvalidRequestError,
    RegionNotFoundError,
)
from app.domain.queries import DateWindow, PlannedQuery, Provider, place_for
from app.domain.schedule import RunWindow
from app.domain.search import SearchTrigger
from app.domain.sources import SOURCES, Source, resolve_sources, source_of


@dataclass(frozen=True, slots=True)
class SearchRequest:
    """Lo que pide quien busca.

    Attributes:
        user_id: Quién busca.
        concept_ids: Conceptos (al menos uno, sin repetir).
        region_id: Región.
        window: Rango de fechas.
        providers: Fuentes que encendió el analista (switches, ADR-0027), o
            ``None`` para usar las de por defecto.
        trigger: Quién la lanza (F12.8): una persona o el reloj.
        scheduled_for: Hora programada de una corrida automática.
        time_window: Horas que cubre una corrida automática (``run_window``);
            ``None`` en las manuales.
        category_ids: Subdivisiones (02/11/2026): se aplican a los conceptos
            que no son temas generales, como la FGR. Cada nota debe traer las
            palabras del concepto y las de una subdivisión.
        default_sources: Fuentes por defecto de esta búsqueda si el analista
            no eligió, en lugar de ``MANUAL_DEFAULT_SOURCES``. La búsqueda
            rápida suma Google web (``QUICK_DEFAULT_SOURCES``, ADR-0115).
    """

    user_id: str
    concept_ids: tuple[int, ...]
    region_id: int
    window: DateWindow
    providers: tuple[Provider, ...] | None = None
    trigger: SearchTrigger = SearchTrigger.MANUAL
    scheduled_for: datetime | None = None
    time_window: RunWindow | None = None
    category_ids: tuple[int, ...] = ()
    default_sources: tuple[Provider, ...] | None = None


@dataclass(frozen=True, slots=True)
class SearchEstimate:
    """La búsqueda armada y lo que costaría.

    Attributes:
        search: Datos para crear la fila de ``searches``.
        breadcrumb: Región elegida ("México › Jalisco").
        queries: Consultas que se enviarían.
        credits: Créditos de SearchApi estimados.
        credits_month: Créditos ya gastados este mes.
        credits_limit: Tope mensual (``SEARCHAPI_MONTHLY_CREDIT_LIMIT``).
        llm: IA que se usaría y su tarifa.
        llm_max_articles: Tope de notas para la IA.
        llm_max_cost_usd: Costo si se enriquece el tope completo.
        credits_balance: Saldo real de la cuenta de SearchApi; ``None`` si
            la búsqueda no gasta créditos o no se pudo leer (entonces solo
            cuenta el tope local).
    """

    search: NewSearch
    breadcrumb: str
    queries: tuple[PlannedQuery, ...]
    credits: int
    credits_month: int
    credits_limit: int
    llm: LLMInfo
    llm_max_articles: int
    llm_max_cost_usd: float
    credits_balance: int | None = None

    @property
    def over_balance(self) -> bool:
        """``True`` si la cuenta de SearchApi no tiene saldo para estas consultas."""
        return self.credits_balance is not None and self.credits > self.credits_balance

    @property
    def over_limit(self) -> bool:
        """``True`` si las consultas pasarían el tope mensual o el saldo de la cuenta."""
        return self.credits_month + self.credits > self.credits_limit or self.over_balance


@dataclass(frozen=True, slots=True)
class SourceOption:
    """Un switch de fuente tal como lo ve el analista (F12.2, ADR-0027).

    Attributes:
        source: La fuente (nombre en pantalla y si cuesta).
        configured: Si tiene lo necesario para consultar; si no, el switch
            se ve apagado y deshabilitado.
        default_on: Si va encendida al abrir la búsqueda. Una de pago solo
            si le quedan créditos (``credits_remaining > 0``).
        quick_default_on: Lo mismo para la búsqueda rápida, que tiene sus
            propias fuentes por defecto (``QUICK_DEFAULT_SOURCES``, con
            Google web; ADR-0115). La pantalla la usa mientras el analista no
            toque los switches.
        credits_remaining: En las de pago configuradas, los créditos que se
            pueden gastar: el menor entre el saldo real de la cuenta y lo que
            deja el tope mensual local (solo el tope si el saldo no se pudo
            leer). ``None`` en las gratuitas y en las no configuradas.
    """

    source: Source
    configured: bool
    default_on: bool
    credits_remaining: int | None = None
    quick_default_on: bool = False


class PlanSearch:
    """Arma una búsqueda con los datos guardados y calcula su costo."""

    def __init__(  # noqa: PLR0913 — una dependencia por dato de la estimación, todo por nombre (*)
        self,
        *,
        concepts: ConceptRepositoryPort,
        regions: RegionRepositoryPort,
        providers: Mapping[Provider, NewsProviderPort],
        log: ProviderQueryLogPort,
        llm: LLMInfo,
        llm_max_articles: int,
        credits_limit: int,
        default_sources: Sequence[Provider] = tuple(Provider),
        quick_default_sources: Sequence[Provider] | None = None,
        balance: CreditBalancePort | None = None,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        """Recibe las piezas.

        Args:
            concepts: Conceptos guardados.
            regions: Catálogo.
            providers: Proveedores; solo se planea con los configurados.
            log: Registro de peticiones (créditos del mes).
            llm: IA elegida y su tarifa.
            llm_max_articles: ``LLM_MAX_ARTICLES_PER_SEARCH``.
            credits_limit: ``SEARCHAPI_MONTHLY_CREDIT_LIMIT``.
            default_sources: Fuentes encendidas si el analista no elige
                (``MANUAL_DEFAULT_SOURCES``); por defecto, todas.
            quick_default_sources: Las de la búsqueda rápida
                (``QUICK_DEFAULT_SOURCES``); ``None``, las mismas que
                ``default_sources``. Solo se usan para pintar los switches:
                la búsqueda rápida las aplica en ``StartQuickSearch``.
            balance: Saldo real de la cuenta de SearchApi; ``None`` (las
                corridas automáticas, ``make buscar`` o sin llave) usa solo el
                tope mensual local.
            now: Reloj (las pruebas lo fijan).
        """
        self._concepts = concepts
        self._regions = regions
        self._providers = providers
        self._log = log
        self._llm = llm
        self._llm_max_articles = llm_max_articles
        self._credits_limit = credits_limit
        self._default_sources = tuple(default_sources)
        self._quick_default_sources = (
            self._default_sources if quick_default_sources is None else tuple(quick_default_sources)
        )
        self._balance = balance
        self._now = now

    def available_providers(self) -> tuple[Provider, ...]:
        """Proveedores con los que se planea de verdad, en su orden.

        Los que no están configurados (sin llave, o apagados como GDELT,
        ADR-0012, o el RSS de Google si se apaga, ADR-0021) no reciben
        consultas. "Probar concepto" usa esta misma lista para mostrar lo que
        una búsqueda mandaría.

        Returns:
            Los proveedores configurados.
        """
        return tuple(p for p, adapter in self._providers.items() if adapter.is_configured())

    def offered_providers(self) -> tuple[Provider, ...]:
        """Los configurados que el analista puede elegir como switch, en su orden.

        «Probar concepto» los usa para mostrar lo que una búsqueda podría
        mandar: sin fuentes ocultas (BrowserWork, ADR-0028) aunque estén
        configuradas.

        Returns:
            Los proveedores configurados que se ofrecen como fuente.
        """
        return tuple(p for p in self.available_providers() if source_of(p) is not None)

    async def _month_used(self) -> int:
        """Lo gastado en el mes por toda la cuenta de SearchApi.

        Google News y Google web comparten créditos y tope (ADR-0115).
        """
        return await self._log.credits_used_since(
            [p.value for p in account_providers(Provider.SEARCHAPI)],
            month_start(self._now(), MEXICO_CITY),
        )

    async def credits_available(self) -> int:
        """Créditos de SearchApi que se pueden gastar ahora.

        Returns:
            El menor entre el saldo real de la cuenta y lo que deja el tope
            mensual local; si el saldo no se puede leer, solo el tope local.
            Nunca negativo.
        """
        local = max(0, self._credits_limit - await self._month_used())
        account = await self._balance.remaining() if self._balance is not None else None
        return local if account is None else min(local, account)

    async def source_options(self) -> list[SourceOption]:
        """Los switches de fuentes de la búsqueda manual, en orden de pantalla.

        Una fuente de pago (SearchApi) solo va encendida por defecto si le
        quedan créditos: así Google web no se lanza solo con la cuenta en 0
        (revisión del 18/11/2026). El saldo se lee una vez para todas. Cada
        opción dice si va encendida en la manual (``default_on``) y en la
        rápida (``quick_default_on``).

        Returns:
            Una opción por fuente del catálogo, configurada o no.
        """
        configured = set(self.available_providers())
        paid = any(s.paid and s.provider in configured for s in SOURCES)
        remaining = await self.credits_available() if paid else None
        options: list[SourceOption] = []
        for source in SOURCES:
            usable = source.provider in configured
            left = remaining if source.paid and usable else None
            affordable = left is None or left > 0
            ready = usable and affordable
            options.append(
                SourceOption(
                    source=source,
                    configured=usable,
                    default_on=source.provider in self._default_sources and ready,
                    credits_remaining=left,
                    quick_default_on=source.provider in self._quick_default_sources and ready,
                )
            )
        return options

    async def _topic_of(
        self, category_ids: Sequence[int]
    ) -> tuple[tuple[str, ...], tuple[str, ...]]:
        """Palabras y exclusiones de las subdivisiones elegidas (las de su tema general)."""
        if len(set(category_ids)) != len(category_ids):
            raise InvalidRequestError(
                "Una subdivisión está repetida.", {"category_ids": list(category_ids)}
            )
        terms: list[str] = []
        exclusions: list[str] = []
        for category_id in category_ids:
            topic = await self._concepts.for_category(category_id)
            if topic is None or not topic.data.is_active:
                raise InvalidRequestError(
                    "Esa subdivisión no tiene palabras clave para buscar.",
                    {"category_id": category_id},
                )
            terms.extend(topic.data.keywords)
            exclusions.extend(topic.data.exclude_terms)
        return tuple(dict.fromkeys(terms)), tuple(dict.fromkeys(exclusions))

    async def _concepts_of(
        self, ids: Sequence[int], category_ids: Sequence[int] = ()
    ) -> tuple[SearchConcept, ...]:
        if not ids:
            raise InvalidRequestError("Elige al menos un concepto.")
        if len(set(ids)) != len(ids):
            raise InvalidRequestError("Un concepto está repetido.", {"concept_ids": list(ids)})
        topic_terms, topic_exclusions = await self._topic_of(category_ids)
        found = []
        for concept_id in ids:
            concept = await self._concepts.get(concept_id)
            if concept is None:
                raise ConceptNotFoundError("No existe ese concepto.", {"id": concept_id})
            if not concept.data.is_active:
                raise InvalidRequestError(
                    f'El concepto "{concept.data.name}" está desactivado.', {"id": concept_id}
                )
            data = concept.data
            # Un tema general («Homicidio») ya es la subdivisión: no se le
            # agrega otra. Las subdivisiones van con la FGR y los demás.
            with_topic = bool(category_ids) and concept.category_id is None
            found.append(
                SearchConcept(
                    concept.id,
                    data.name,
                    data.description,
                    data.keywords,
                    tuple(dict.fromkeys((*data.exclude_terms, *topic_exclusions)))
                    if with_topic
                    else data.exclude_terms,
                    topic_terms if with_topic else (),
                    tuple(category_ids) if with_topic else (),
                    data.query_mode,
                    data.required_terms,
                )
            )
        if category_ids and not any(c.category_ids for c in found):
            raise InvalidRequestError(
                "Las subdivisiones van con un concepto como la FGR, no solas.",
                {"category_ids": list(category_ids)},
            )
        return tuple(found)

    async def estimate(self, request: SearchRequest) -> SearchEstimate:
        """Planea la búsqueda sin gastar nada.

        Args:
            request: Conceptos, región y fechas.

        Returns:
            Las consultas y el costo.

        Raises:
            InvalidRequestError: Sin conceptos, con conceptos repetidos o
                desactivados, sin fuentes o con una fuente no configurada.
            ConceptNotFoundError: Si un concepto no existe o fue borrado.
            RegionNotFoundError: Si la región no existe.
            QueryTooLongError: Si una palabra clave no cabe en un proveedor.
        """
        concepts = await self._concepts_of(request.concept_ids, request.category_ids)
        region = await self._regions.get(request.region_id)
        facts = await self._regions.place_facts(request.region_id) if region else None
        if region is None or facts is None:
            raise RegionNotFoundError("No existe esa región.", {"id": request.region_id})
        ancestors = await self._regions.ancestors(region.id)
        available = self.available_providers()
        # Sin ningún proveedor configurado no hay nada que elegir: StartSearch
        # responde «no hay proveedores disponibles» (503), como antes de F12.2.
        defaults = (
            request.default_sources
            if request.default_sources is not None
            else self._default_sources
        )
        sources = resolve_sources(request.providers, defaults, available) if available else ()
        queries = tuple(plan_queries(concepts, place_for(facts), request.window, sources))
        credits_estimated = sum(self._providers[q.provider].estimate_cost(q) for q in queries)
        used = await self._month_used()
        # El saldo real solo importa si la búsqueda gasta: así una búsqueda
        # gratis no espera a SearchApi.
        balance = (
            await self._balance.remaining()
            if self._balance is not None and credits_estimated > 0
            else None
        )
        window = request.window
        return SearchEstimate(
            search=NewSearch(
                user_id=request.user_id,
                region_id=region.id,
                date_from=window.date_from,
                date_to=window.date_to,
                concepts=concepts,
                queries_planned=len(queries),
                credits_estimated=credits_estimated,
                providers=sources,
                trigger=request.trigger,
                scheduled_for=request.scheduled_for,
                time_window=request.time_window,
            ),
            breadcrumb=" › ".join([*(a.name for a in ancestors), region.name]),
            queries=queries,
            credits=credits_estimated,
            credits_month=used,
            credits_limit=self._credits_limit,
            llm=self._llm,
            llm_max_articles=self._llm_max_articles,
            llm_max_cost_usd=estimated_usage(self._llm_max_articles).cost_usd(
                self._llm.price_input_per_million, self._llm.price_output_per_million
            ),
            credits_balance=balance,
        )
