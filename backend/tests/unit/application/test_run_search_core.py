"""RunSearch con el filtro de palabras del pedido (ADR-0114), con piezas en memoria."""

from collections.abc import Mapping
from pathlib import Path
from uuid import uuid4

import pytest

from app.adapters.providers.searchapi_web import parse_page, untruncated
from app.application.ports.search_store import SearchConcept
from app.application.use_cases.run_search import (
    OFF_CORE_SAMPLES,
    RunSearch,
    core_of,
    plan_queries,
    unconfirmed_matcher,
)
from app.domain.articles import RawArticle
from app.domain.concept import QueryMode
from app.domain.core_terms import CoreTerms, QueryOrigin
from app.domain.queries import Provider, QueryPlace
from tests.unit.application.test_execute_queries import MEXICO as MEXICO_FILTER
from tests.unit.application.test_execute_queries import WEEK
from tests.unit.application.test_run_search import (
    EXTORSION,
    IZTA_SEARCHAPI,
    IZTA_TITLE,
    LLM,
    MADRID,
    MADRID_TITLE,
    Articles,
    Extractor,
    Searches,
    Source,
    enrichment,
    pipeline,
    raw,
    stored_search,
)

pytestmark = pytest.mark.anyio

# La búsqueda rápida «hacker eternal» (ADR-0113): «eternal» es obligatorio.
RAPIDA = SearchConcept(
    9,
    "hacker eternal",
    "hacker eternal",
    ("hacker eternal",),
    query_mode=QueryMode.OPEN,
    required_terms=("eternal",),
)
ETERNAL_TITLE = "El hacker Eternal filtra datos del IMSS"
# Real (Google News RSS, 18/11/2026): no nombra a Eternal en el título.
BURO_TITLE = "Hackean Buró Laboral y exponen datos de miles de trabajadores"
FEMINIST_TITLE = "Concentración feminista en Guadalajara"
MOVIE_TITLE = "Eternal Sunshine vuelve a los cines"
SAT_TITLE = "Hackean el SAT y exponen datos de contribuyentes"
ETERNAL = raw(Provider.SEARCHAPI, 1, "https://milenio.com/eternal", ETERNAL_TITLE)
BURO = raw(Provider.SEARCHAPI, 2, "https://eluniversal.com.mx/buro", BURO_TITLE)
FEMINIST = raw(Provider.SEARCHAPI, 3, "https://informador.mx/marcha", FEMINIST_TITLE)
MOVIE = raw(Provider.SEARCHAPI, 4, "https://cine.mx/eternal", MOVIE_TITLE)
# El índice local solo busca en título y resumen: no cuenta la procedencia y
# sí se le exige el tema.
SAT_LOCAL = raw(Provider.LOCAL_INDEX, 1, "https://excelsior.com.mx/sat", SAT_TITLE)
BURO_LOCAL = raw(Provider.LOCAL_INDEX, 2, "https://eluniversal.com.mx/buro", BURO_TITLE)
FEMINIST_LOCAL = raw(Provider.LOCAL_INDEX, 3, "https://informador.mx/marcha-local", FEMINIST_TITLE)
MOVIE_LOCAL = raw(Provider.LOCAL_INDEX, 4, "https://cine.mx/eternal-local", MOVIE_TITLE)
PLACE = QueryPlace(("Iztapalapa",), (), MEXICO_FILTER)
# Respuesta real de Google web a «hacker eternal» (18/11/2026), con sus 4
# videos del carrusel.
WEB_FIXTURE = (
    Path(__file__).resolve().parents[2] / "fixtures" / "providers"
) / "searchapi_web_hacker_eternal_7d.json"


def samples(progress: Mapping[str, object]) -> list[str]:
    value = progress["off_core_samples"]
    assert isinstance(value, list)
    return [str(t) for t in value]


def eternal_pipeline() -> tuple[RunSearch, Searches, Articles, LLM, Extractor]:
    return pipeline(
        sources=[
            Source(Provider.SEARCHAPI, [ETERNAL, BURO], cost=1),
            Source(Provider.LOCAL_INDEX, [SAT_LOCAL, FEMINIST_LOCAL, MOVIE_LOCAL]),
        ],
        search=stored_search(RAPIDA),
        replies={ETERNAL_TITLE: enrichment(), BURO_TITLE: enrichment()},
    )


async def test_lo_que_no_habla_de_lo_pedido_ni_se_guarda_ni_se_paga() -> None:
    use_case, searches, articles, llm, _ = eternal_pipeline()

    report = await use_case.run(uuid4())

    assert sorted(r.title for r in llm.requests) == sorted([ETERNAL_TITLE, BURO_TITLE])
    assert sorted(articles.ids) == [
        "https://eluniversal.com.mx/buro",
        "https://milenio.com/eternal",
    ]
    assert report.articles == 2
    last = searches.progress[-1]
    assert last["off_core"] == 3
    assert sorted(samples(last)) == sorted([FEMINIST_TITLE, MOVIE_TITLE, SAT_TITLE])


async def test_lo_que_trajo_google_news_sin_el_tema_llega_al_juez() -> None:
    # Revisión del 18/11/2026 (hallazgo 2): SearchApi ya exigió las palabras en
    # el cuerpo de la nota; el filtro de título ya no la tira por tema. Que
    # decida el juez y la banda «ajena» la esconda.
    use_case, searches, _, llm, _ = pipeline(
        sources=[Source(Provider.SEARCHAPI, [ETERNAL, FEMINIST, MOVIE], cost=1)],
        search=stored_search(RAPIDA),
        replies={
            ETERNAL_TITLE: enrichment(),
            FEMINIST_TITLE: enrichment(relevant=False),
            MOVIE_TITLE: enrichment(relevant=False),
        },
    )

    await use_case.run(uuid4())

    assert sorted(r.title for r in llm.requests) == sorted(
        [ETERNAL_TITLE, FEMINIST_TITLE, MOVIE_TITLE]
    )
    by_title = {r.title: r for r in llm.requests}
    # La marcha no nombra a Eternal: el juez sabe que falta confirmarlo.
    assert by_title[FEMINIST_TITLE].unconfirmed_terms == ("eternal",)
    assert by_title[MOVIE_TITLE].unconfirmed_terms == ()
    assert searches.progress[-1]["off_core"] == 0


async def test_con_el_tope_de_la_ia_primero_las_que_nombran_lo_pedido() -> None:
    # Revisión del 18/11/2026: Google News trae primero la del Buró (no nombra
    # a Eternal); con lugar para una sola, la IA juzga la que sí lo nombra.
    use_case, searches, _, llm, _ = pipeline(
        sources=[Source(Provider.SEARCHAPI, [BURO, ETERNAL], cost=1)],
        search=stored_search(RAPIDA),
        replies={ETERNAL_TITLE: enrichment(), BURO_TITLE: enrichment()},
        max_llm_articles=1,
    )

    await use_case.run(uuid4())

    assert [r.title for r in llm.requests] == [ETERNAL_TITLE]
    assert searches.progress[-1]["skipped_by_cap"] == 1


async def test_la_ia_sabe_que_la_nota_paso_por_procedencia() -> None:
    use_case, _, _, llm, _ = eternal_pipeline()

    await use_case.run(uuid4())

    by_title = {r.title: r for r in llm.requests}
    buro, eternal = by_title[BURO_TITLE], by_title[ETERNAL_TITLE]
    assert buro.unconfirmed_terms == ("eternal",)
    assert eternal.unconfirmed_terms == ()
    assert [(o.provider, o.label, o.full_text) for o in buro.origins] == [
        ("searchapi", "SearchApi (Google News)", True)
    ]
    assert buro.origins[0].carries("eternal")
    # El juez sabe dónde se busca (la región de la búsqueda).
    assert buro.region == "Ciudad de México"


def web_videos() -> list[RawArticle]:
    """Los videos del carrusel del fixture, como los arma el adaptador."""
    page = parse_page(WEB_FIXTURE.read_text(encoding="utf-8"))
    videos: list[RawArticle] = []
    for hit in page.hits:
        if hit.section != "inline_videos":
            continue
        title, truncated = untruncated(hit.title)
        videos.append(
            RawArticle.create(
                provider=Provider.SEARCHAPI_WEB,
                provider_rank=len(videos) + 1,
                url=hit.link,
                title=title,
                source_name=hit.source_name,
                snippet=hit.snippet,
                raw=hit.raw,
                title_truncated=truncated,
            )
        )
    return videos


async def test_de_los_videos_de_google_web_solo_pasa_el_que_nombra_a_eternal() -> None:
    # Revisión del 18/11/2026 (hallazgo 3): un carrusel no busca en el texto de
    # la nota; sin «Eternal» en título, fragmento o canal no es lo pedido.
    videos = web_videos()
    la_saga = "ETERNAL expone 746 MIL cuentas de PILLOFON y ya clonan"
    assert len(videos) == 4
    use_case, searches, _, llm, _ = pipeline(
        sources=[Source(Provider.SEARCHAPI_WEB, videos, cost=1)],
        search=stored_search(RAPIDA),
        replies={la_saga: enrichment()},
    )

    await use_case.run(uuid4())

    assert [r.title for r in llm.requests] == [la_saga]
    assert llm.requests[0].origins[0].section == "inline_videos"
    assert not llm.requests[0].origins[0].full_text
    last = searches.progress[-1]
    assert last["off_core"] == 3
    assert sorted(samples(last)) == sorted(v.title for v in videos[1:])


async def test_el_juez_sabe_lo_que_otras_notas_dicen_de_la_entidad() -> None:
    # Revisión del 18/11/2026 (hallazgo 4): sin esto, cualquier nota del tema
    # de solo título salía «por confirmar».
    use_case, _, _, llm, _ = eternal_pipeline()

    await use_case.run(uuid4())

    by_title = {r.title: r for r in llm.requests}
    assert by_title[BURO_TITLE].entity_context == (ETERNAL_TITLE,)
    # La que sí nombra a Eternal no necesita contexto.
    assert by_title[ETERNAL_TITLE].entity_context == ()


async def test_los_titulos_de_muestra_tienen_tope() -> None:
    noise = [
        raw(Provider.LOCAL_INDEX, i, f"https://ruido.mx/{i}", f"Concierto número {i} en el Zócalo")
        for i in range(2, OFF_CORE_SAMPLES + 5)
    ]
    use_case, searches, _, llm, _ = pipeline(
        sources=[
            Source(Provider.SEARCHAPI, [ETERNAL], cost=1),
            Source(Provider.LOCAL_INDEX, noise),
        ],
        search=stored_search(RAPIDA),
        replies={ETERNAL_TITLE: enrichment()},
    )

    await use_case.run(uuid4())

    last = searches.progress[-1]
    assert last["off_core"] == OFF_CORE_SAMPLES + 3
    assert len(samples(last)) == OFF_CORE_SAMPLES
    assert [r.title for r in llm.requests] == [ETERNAL_TITLE]


async def test_un_concepto_exacto_no_se_filtra_por_palabras() -> None:
    # ADR-0109 D2: la FGR y los temas se quedan como estaban.
    use_case, searches, articles, llm, _ = pipeline()

    report = await use_case.run(uuid4())

    assert report.articles == 2
    assert sorted(r.title for r in llm.requests) == sorted([IZTA_TITLE, MADRID_TITLE])
    assert all("off_core" not in p for p in searches.progress)
    assert all(r.origins == () and r.unconfirmed_terms == () for r in llm.requests)
    assert len(articles.ids) == 2


async def test_lo_que_trae_un_concepto_exacto_se_queda_aunque_el_abierto_lo_tire() -> None:
    # Los proveedores falsos devuelven lo mismo a cada consulta: la nota de
    # extorsión llega por la consulta exacta y por la abierta.
    use_case, searches, _, llm, _ = pipeline(
        sources=[Source(Provider.SEARCHAPI, [IZTA_SEARCHAPI, MADRID, ETERNAL], cost=1)],
        search=stored_search(EXTORSION, RAPIDA),
        replies={
            IZTA_TITLE: enrichment(),
            MADRID_TITLE: enrichment(),
            ETERNAL_TITLE: enrichment(),
        },
    )

    await use_case.run(uuid4())

    assert sorted(r.title for r in llm.requests) == sorted(
        [IZTA_TITLE, MADRID_TITLE, ETERNAL_TITLE]
    )
    assert searches.progress[-1]["off_core"] == 0


def test_solo_las_consultas_de_un_concepto_abierto_llevan_lo_pedido() -> None:
    queries = plan_queries([EXTORSION, RAPIDA], PLACE, WEEK, [Provider.LOCAL_INDEX])

    assert [(q.keywords, q.core) for q in queries] == [
        (("extorsión", "cobro de piso"), None),
        (("hacker eternal",), CoreTerms(("eternal",), ("HACK",))),
    ]


def test_el_lugar_de_la_busqueda_no_cuenta_como_tema() -> None:
    robos = SearchConcept(
        4,
        "Robo de autos",
        "robo de autos en Iztapalapa",
        ("robo de autos Iztapalapa",),
        query_mode=QueryMode.OPEN,
    )

    assert core_of(robos, PLACE) == CoreTerms((), ("ROB", "AUT"))
    assert core_of(EXTORSION, PLACE) is None


def test_las_entidades_sin_confirmar_salen_de_los_conceptos_abiertos() -> None:
    exacto_con_terminos = SearchConcept(
        3, "Extorsión", "Cobro de piso", ("extorsión",), required_terms=("CJNG",)
    )

    matcher = unconfirmed_matcher([exacto_con_terminos, RAPIDA])

    assert matcher is not None
    assert matcher.missing_terms(BURO_TITLE, None) == ("eternal",)
    assert unconfirmed_matcher([EXTORSION]) is None


async def test_lo_que_trae_el_indice_local_sin_la_entidad_no_pasa_por_procedencia() -> None:
    use_case, searches, _, llm, _ = pipeline(
        sources=[Source(Provider.LOCAL_INDEX, [ETERNAL, BURO_LOCAL])],
        search=stored_search(RAPIDA),
        replies={ETERNAL_TITLE: enrichment()},
    )

    await use_case.run(uuid4())

    assert [r.title for r in llm.requests] == [ETERNAL_TITLE]
    assert samples(searches.progress[-1]) == [BURO_TITLE]
    local = llm.requests[0].origins
    assert [(o.provider, o.full_text) for o in local] == [("indice_local", False)]
    assert local == (
        QueryOrigin("indice_local", "Índice local (GDELT + medios)", ("hacker eternal",), False),
    )
