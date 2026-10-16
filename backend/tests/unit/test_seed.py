"""El archivo de conceptos semilla cumple las reglas del dominio."""

from datetime import date

from app.domain.queries import CountryFilter, DateWindow, QueryPlace
from app.domain.query_builder import build_queries
from app.seed.cargar_conceptos import read_seed

EXPECTED = [
    "Ciberseguridad",
    "Secuestro",
    "Extorsión",
    "Robo de vehículos",
    "Desaparición de personas",
]
MEXICO = CountryFilter("México", "MX", "MX", "Mexico")
WEEK = DateWindow.last_days(7, date(2026, 10, 16))


def test_los_cinco_conceptos_de_la_especificacion_son_validos() -> None:
    drafts = [c.validated() for c in read_seed()]

    assert [d.name for d in drafts] == EXPECTED
    assert len({d.color for d in drafts}) == len(drafts)


def test_cada_semilla_cabe_en_una_consulta_por_proveedor_en_un_lugar_comun() -> None:
    place = QueryPlace(("Iztapalapa",), (), MEXICO)

    for draft in (c.validated() for c in read_seed()):
        assert len(build_queries(draft, place, WEEK)) == 3, draft.name


def test_con_un_nombre_oficial_largo_se_parte_sin_perder_palabras() -> None:
    # Medido: con el límite prudente de 32 palabras (VERIFICAR en F3),
    # "Robo de vehículos" en Juchitán necesita 2 consultas de SearchApi.
    place = QueryPlace(("Heroica Ciudad de Juchitán de Zaragoza",), ("Oaxaca",), MEXICO)

    for draft in (c.validated() for c in read_seed()):
        queries = [q for q in build_queries(draft, place, WEEK) if q.provider == "searchapi"]
        assert tuple(k for q in queries for k in q.keywords) == draft.keywords, draft.name
