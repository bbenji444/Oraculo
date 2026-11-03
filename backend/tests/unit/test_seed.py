"""El archivo de conceptos semilla cumple las reglas del dominio."""

from datetime import date

from app.domain.authority import RelevanceRule
from app.domain.queries import CountryFilter, DateWindow, Provider, QueryPlace
from app.domain.query_builder import build_queries
from app.seed.cargar_conceptos import read_rules, read_seed, read_topics

# Desde F12.6 la semilla es solo el concepto de la FGR (plan F12 §4.8).
# Con acentos desde el 27/10/2026: sin ellos Google News traía 4 notas (migración 0031).
EXPECTED = ["Fiscalía General de la República"]
MEXICO = CountryFilter("México", "MX", "MX", "Mexico")
WEEK = DateWindow.last_days(7, date(2026, 10, 16))


def test_la_semilla_es_el_concepto_fgr_valido_y_con_su_regla() -> None:
    drafts = [c.validated() for c in read_seed()]

    assert [d.name for d in drafts] == EXPECTED
    assert len({d.color for d in drafts}) == len(drafts)
    assert read_rules() == {"FISCALIA GENERAL DE LA REPUBLICA": RelevanceRule.FGR_FEDERAL}


def test_cada_semilla_cabe_en_una_consulta_por_proveedor_en_un_lugar_comun() -> None:
    # Google News RSS va una consulta por palabra clave (tope de 100 notas).
    place = QueryPlace(("Iztapalapa",), (), MEXICO)

    for draft in (c.validated() for c in read_seed()):
        queries = build_queries(draft, place, WEEK)
        rss = [q for q in queries if q.provider == Provider.GOOGLE_NEWS_RSS]
        assert len(rss) == len(draft.keywords), draft.name
        assert len(queries) - len(rss) == len(Provider) - 1, draft.name


def test_con_un_nombre_oficial_largo_se_parte_sin_perder_palabras() -> None:
    # Medido: con el límite prudente de 32 palabras (VERIFICAR en F3), un
    # concepto largo en Juchitán necesita 2 consultas de SearchApi.
    place = QueryPlace(("Heroica Ciudad de Juchitán de Zaragoza",), ("Oaxaca",), MEXICO)

    for draft in (c.validated() for c in read_seed()):
        queries = [q for q in build_queries(draft, place, WEEK) if q.provider == "searchapi"]
        assert tuple(k for q in queries for k in q.keywords) == draft.keywords, draft.name


# --- Temas generales de las subdivisiones (02/11/2026) ---

# Las 15 subdivisiones de las migraciones 0026 y 0029, menos «Otros».
SUBDIVISIONS = [
    "Narcotráfico y delitos contra la salud",
    "Delincuencia organizada",
    "Secuestro",
    "Desaparición de personas",
    "Homicidio",
    "Armas y explosivos",
    "Huachicol y delitos contra hidrocarburos",
    "Lavado de dinero y delitos fiscales",
    "Corrupción",
    "Trata de personas",
    "Extorsión",
    "Ciberdelitos",
    "Delitos electorales",
    "Seguridad nacional (traición a la patria)",
]
# Tope de consultas de SearchApi (un crédito cada una) por tema en una semana.
MAX_TOPIC_CREDITS_ALONE = 2
MAX_TOPIC_CREDITS_WITH_FGR = 3


def test_hay_un_tema_valido_por_subdivision_menos_otros() -> None:
    topics = read_topics()

    assert [t.category for t in topics] == SUBDIVISIONS
    for topic in topics:
        draft = topic.concept.validated()
        assert draft.name == topic.category
        assert len(set(draft.keywords)) == len(draft.keywords), draft.name


def test_cada_tema_cabe_solo_y_junto_con_la_fgr() -> None:
    [fgr] = [c.validated() for c in read_seed()]
    place = QueryPlace(("Iztapalapa",), (), MEXICO)

    for topic in (t.concept.validated() for t in read_topics()):
        alone = build_queries(topic, place, WEEK, [Provider.SEARCHAPI])
        together = build_queries(fgr, place, WEEK, [Provider.SEARCHAPI], topic_terms=topic.keywords)
        # Medido el 02/11/2026 con el límite de 32 palabras: por SearchApi un
        # tema cuesta 1 o 2 créditos solo y hasta 3 con la FGR; sin perder palabras.
        assert len(alone) <= MAX_TOPIC_CREDITS_ALONE, topic.name
        assert len(together) <= MAX_TOPIC_CREDITS_WITH_FGR, topic.name
        assert tuple(k for q in alone for k in q.keywords) == topic.keywords, topic.name
        chunks = list(dict.fromkeys(q.topic_terms for q in together))
        assert tuple(t for chunk in chunks for t in chunk) == topic.keywords, topic.name
