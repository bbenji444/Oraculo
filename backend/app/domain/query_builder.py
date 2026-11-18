"""Constructor de consultas (``build_queries``, especificación §7.2).

Convierte un concepto, un lugar y un rango de fechas en las consultas que
se enviarían a cada proveedor. Lo usan "Probar concepto" (F2), que las
muestra sin gastar créditos, y el pipeline de búsqueda (F4), que las
ejecuta.

Regla de §7.2: **una consulta por proveedor y concepto**, con las palabras
clave unidas por OR. Si el texto excede el límite del proveedor, las
palabras clave se reparten en varias consultas, conservando el orden.

Excepción: un proveedor gratis con tope de notas por respuesta (Google News
RSS, 100) se parte por palabra clave y, en ventanas cortas, por día, sin
pasar de ``QueryDialect.split_up_to`` consultas. Con OR las palabras
compiten por las mismas 100 notas y la sigla «FGR» tapaba al nombre completo.

En modo «como en Google» (ADR-0109) ese proveedor recibe cada frase sola y
sin comillas, nunca juntas con OR: así se escriben los titulares y así
rinden. Los demás proveedores juntan las frases como siempre, con comillas.

Con subdivisión (02/11/2026, «FGR + Homicidio»), cada consulta lleva un
segundo grupo con las palabras del tema, que también deben aparecer. Si ese
grupo no cabe en el límite del proveedor, se parte en varios y cada parte
lleva sus propias consultas.

Google web (``literal_only``, ADR-0115) recibe **una sola** consulta: la
primera palabra clave tal cual, más el lugar si la región es un estado o
municipio. Sin OR, sin comillas ni exclusiones, como se busca en Google:
ese buscador trae redes sociales y sitios que no son de noticias, y cada
consulta cuesta un crédito.

No hace: no aplica los topes por búsqueda (``MAX_QUERIES_PER_SEARCH`` y
``MAX_FREE_QUERIES_PER_SEARCH``) ni la caché; eso es de la búsqueda completa (F3/F4).
"""

from collections.abc import Sequence
from datetime import date, timedelta
from typing import Protocol

from app.domain.concept import OPEN_MAX_PHRASES, QueryMode
from app.domain.errors import ConceptValidationError, QueryTooLongError
from app.domain.queries import (
    SEARCH_LANGUAGE,
    DateWindow,
    PlannedQuery,
    Provider,
    QueryPlace,
)
from app.domain.query_dialects import DIALECTS, QueryDialect

# Ventanas de fechas fijas de hasta tantos días se parten por día. Con más, las
# consultas no cabrían en el tope por búsqueda (se eligió con el de 10, que
# contaba todas; desde ADR-0109 las gratuitas tienen su tope de 24).
SPLIT_MAX_DAYS = 3


class ConceptTerms(Protocol):
    """Lo que ``build_queries`` necesita de un concepto (guardado o borrador)."""

    @property
    def keywords(self) -> tuple[str, ...]:
        """Palabras clave."""
        ...

    @property
    def exclude_terms(self) -> tuple[str, ...]:
        """Exclusiones."""
        ...

    @property
    def query_mode(self) -> QueryMode:
        """Frases exactas o «como en Google» (ADR-0109)."""
        ...


def _split_keywords(
    dialect: QueryDialect,
    concept: ConceptTerms,
    place: QueryPlace,
    window: DateWindow,
    topic: tuple[str, ...] = (),
) -> list[tuple[str, ...]]:
    """Reparte las palabras clave en grupos que quepan en el límite del proveedor."""

    def fits(chunk: Sequence[str]) -> bool:
        return dialect.fits(dialect.render(chunk, place, concept.exclude_terms, window, topic))

    chunks: list[tuple[str, ...]] = []
    current: list[str] = []
    for keyword in concept.keywords:
        if fits([*current, keyword]):
            current.append(keyword)
            continue
        if not fits([keyword]):
            raise QueryTooLongError(
                f"La consulta para {dialect.label} no cabe en su límite ni con una sola "
                "palabra clave. Reduce las exclusiones o usa palabras más cortas.",
                {"proveedor": dialect.provider.value, "palabra": keyword},
            )
        chunks.append(tuple(current))
        current = [keyword]
    chunks.append(tuple(current))
    return chunks


def _days(window: DateWindow) -> list[DateWindow]:
    """Los días de una ventana fija corta, uno por uno; si no, la ventana entera.

    «Últimos N días» no se parte: ``when:Nd`` cuenta horas hacia atrás desde
    ahora y un día de calendario no equivale a eso.
    """
    span = (window.date_to - window.date_from).days + 1
    if window.relative_days is not None or not 1 < span <= SPLIT_MAX_DAYS:
        return [window]
    return [
        DateWindow.between(day, day)
        for day in (window.date_from + timedelta(days=i) for i in range(span))
    ]


def manual_window(date_from: date, date_to: date, today: date) -> DateWindow:
    """La ventana con la que corre una búsqueda manual ya guardada (ADR-0113).

    ``searches`` guarda solo las fechas, así que «últimos 7 días» llegaba al
    pipeline como un rango fijo: Google News RSS recibía ``after:``/``before:``,
    que no respeta (medido el 16/10/2026), en lugar del ``when:7d`` que sí
    muestra la vista previa. Si la ventana termina hoy y pasa de
    ``SPLIT_MAX_DAYS`` días, vuelve a ser «últimos N días»: ``when:Nd`` en el
    RSS, ``time_period`` en SearchApi y ``timespan`` en GDELT.

    Las de 1 a ``SPLIT_MAX_DAYS`` días se quedan fijas a propósito: las de 2
    y 3 se parten por día y traen más notas (medido el 27/10/2026: 281 por
    palabra y por día; solo por palabra, a lo más 200), y «Hoy» con ``when:1d`` contaría 24
    horas hacia atrás y podría llenar el tope de 100 notas con las de ayer,
    que luego se tiran por la ventana estricta.

    Args:
        date_from: Primer día guardado.
        date_to: Último día guardado.
        today: Hoy en la Ciudad de México.

    Returns:
        «Últimos N días» si aplica; si no, el rango fijo.

    Raises:
        InvalidRequestError: Si las fechas están al revés o pasan de 90 días.

    Example:
        >>> manual_window(date(2026, 11, 12), date(2026, 11, 18), date(2026, 11, 18))
        DateWindow(date_from=..., date_to=..., relative_days=7)
    """
    window = DateWindow.between(date_from, date_to)
    span = (date_to - date_from).days + 1
    if date_to == today and span > SPLIT_MAX_DAYS:
        return DateWindow.last_days(span, today)
    return window


def _split_topic(
    dialect: QueryDialect,
    concept: ConceptTerms,
    place: QueryPlace,
    window: DateWindow,
    topic: tuple[str, ...],
) -> list[tuple[str, ...]]:
    """Reparte las palabras de la subdivisión en grupos que quepan con la palabra clave más larga.

    Sin subdivisión devuelve un solo grupo vacío, así el resto del plan no cambia.
    """
    if not topic:
        return [()]
    longest = max(concept.keywords, key=len)

    def fits(chunk: Sequence[str]) -> bool:
        return dialect.fits(
            dialect.render([longest], place, concept.exclude_terms, window, tuple(chunk))
        )

    chunks: list[tuple[str, ...]] = []
    current: list[str] = []
    for term in topic:
        if fits([*current, term]):
            current.append(term)
            continue
        if not current:
            raise QueryTooLongError(
                f"La consulta para {dialect.label} no cabe en su límite con la subdivisión. "
                "Usa palabras más cortas en la subdivisión o menos exclusiones.",
                {"proveedor": dialect.provider.value, "palabra": term},
            )
        chunks.append(tuple(current))
        current = [term]
    chunks.append(tuple(current))
    return chunks


def _plan(
    dialect: QueryDialect,
    concept: ConceptTerms,
    place: QueryPlace,
    window: DateWindow,
    topic: tuple[str, ...] = (),
) -> list[tuple[tuple[str, ...], DateWindow]]:
    """Qué palabras y qué días lleva cada consulta de un proveedor.

    Sin tope de notas, son los grupos de ``_split_keywords`` con la ventana
    completa. Con tope (``split_up_to``) se prueba, en este orden, lo que más
    notas trae sin pasarse: cada palabra cada día, cada grupo cada día, cada
    palabra con la ventana completa y, al final, los grupos.

    En modo abierto (ADR-0109) las frases nunca se juntan con OR en un
    proveedor con tope: cada frase va sola, por día si caben en
    ``OPEN_MAX_PHRASES`` consultas y, si no, con la ventana completa.
    """
    chunks = _split_keywords(dialect, concept, place, window, topic)
    limit = dialect.split_up_to
    if limit is None:
        return [(chunk, window) for chunk in chunks]
    singles = [(keyword,) for keyword in concept.keywords]
    days = _days(window)
    if concept.query_mode is QueryMode.OPEN:
        spans = days if len(singles) * len(days) <= OPEN_MAX_PHRASES else [window]
        return [(single, span) for single in singles for span in spans]
    for groups, spans in ((singles, days), (chunks, days), (singles, [window])):
        if len(groups) * len(spans) <= limit:
            return [(g, span) for g in groups for span in spans]
    return [(chunk, window) for chunk in chunks]


def _literal_query(
    dialect: QueryDialect,
    concept: ConceptTerms,
    place: QueryPlace,
    window: DateWindow,
    topic: tuple[str, ...],
) -> PlannedQuery:
    """La única consulta de un proveedor «como Google» (``literal_only``, ADR-0115).

    Lleva la primera palabra clave tal cual, sin comillas (en la búsqueda
    rápida es lo que escribió el analista), y el lugar si la región es un
    estado, municipio o localidad; en un país o en «Mundo», solo el texto.
    No lleva exclusiones ni la subdivisión en el texto: así se busca en
    Google. La subdivisión sí queda en ``topic_terms`` para que el pipeline
    descarte lo que no la mencione, igual que con los demás proveedores.

    Args:
        dialect: Dialecto del proveedor.
        concept: Concepto (se usa su primera palabra clave).
        place: Lugar.
        window: Rango de fechas (va como parámetro en el adaptador).
        topic: Palabras de la subdivisión, si hay.

    Returns:
        La consulta.

    Raises:
        QueryTooLongError: Si el texto con el lugar no cabe en el límite.
    """
    literal = concept.keywords[0]
    text = dialect.render((literal,), place, (), window, exact=False)
    if not dialect.fits(text):
        raise QueryTooLongError(
            f"La consulta para {dialect.label} no cabe en su límite. Usa un texto más corto.",
            {"proveedor": dialect.provider.value, "palabra": literal},
        )
    return PlannedQuery(
        provider=dialect.provider,
        text=text,
        keywords=(literal,),
        country=place.country,
        language=SEARCH_LANGUAGE,
        window=window,
        estimated_credits=dialect.credits_per_query,
        place=place,
        topic_terms=topic,
    )


def build_queries(
    concept: ConceptTerms,
    place: QueryPlace,
    window: DateWindow,
    providers: Sequence[Provider] = tuple(Provider),
    topic_terms: Sequence[str] = (),
) -> list[PlannedQuery]:
    """Genera las consultas que se enviarían a cada proveedor.

    Args:
        concept: Concepto con palabras clave y exclusiones.
        place: Cómo se nombra el lugar (``queries.place_for``).
        window: Rango de fechas.
        providers: Proveedores a usar, en orden (por defecto todos).
        topic_terms: Palabras de la subdivisión que también deben aparecer
            («FGR + Homicidio»); vacío para buscar solo el concepto.

    Returns:
        Una o más consultas por proveedor. Ninguna se ejecuta: sirven para
        mostrarlas y estimar créditos.

    Raises:
        ConceptValidationError: Si el concepto no tiene palabras clave.
        QueryTooLongError: Si ni una sola palabra clave cabe en el límite.

    Example:
        >>> [q.text for q in build_queries(ciberseguridad, iztapalapa, semana, [Provider.GDELT])]
        ['(ciberataque OR hackeo ...) Iztapalapa -curso ... sourcelang:spanish sourcecountry:MX']
    """
    if not concept.keywords:
        raise ConceptValidationError(
            "El concepto no tiene palabras clave.",
            {"problemas": [{"campo": "keywords", "mensaje": "Agrega al menos una palabra clave."}]},
        )
    topic = tuple(dict.fromkeys(topic_terms))
    is_open = concept.query_mode is QueryMode.OPEN
    queries = []
    for provider in providers:
        dialect = DIALECTS[provider]
        if dialect.literal_only:
            queries.append(_literal_query(dialect, concept, place, window, topic))
            continue
        for topic_chunk in _split_topic(dialect, concept, place, window, topic):
            for chunk, span in _plan(dialect, concept, place, window, topic_chunk):
                # Sin comillas solo la frase que va sola: Google lee
                # «(roban auto OR robo de vehículo)» como roban Y (auto O
                # robo) Y de Y vehículo, así que al juntar frases se conservan.
                exact = not is_open or len(chunk) > 1
                queries.append(
                    PlannedQuery(
                        provider=provider,
                        # El texto lleva el día; ``window`` sigue siendo la
                        # ventana completa porque con ella el adaptador
                        # descarta lo de fuera (Google News RSS no siempre
                        # respeta after:/before:).
                        text=dialect.render(
                            chunk, place, concept.exclude_terms, span, topic_chunk, exact=exact
                        ),
                        keywords=chunk,
                        country=place.country,
                        language=SEARCH_LANGUAGE,
                        window=window,
                        estimated_credits=dialect.credits_per_query,
                        exclude_terms=concept.exclude_terms,
                        place=place,
                        topic_terms=topic_chunk,
                    )
                )
    return queries
