"""El archivo de conceptos semilla cumple las reglas del dominio."""

from datetime import date

from app.domain.authority import RelevanceRule
from app.domain.queries import CountryFilter, DateWindow, Provider, QueryPlace
from app.domain.query_builder import build_queries
from app.seed.cargar_conceptos import read_rules, read_seed

# Desde F12.6 la semilla es solo el concepto de la FGR (plan F12 §4.8).
EXPECTED = ["Fiscalia General de la Republica"]
MEXICO = CountryFilter("México", "MX", "MX", "Mexico")
WEEK = DateWindow.last_days(7, date(2026, 10, 16))


def test_la_semilla_es_el_concepto_fgr_valido_y_con_su_regla() -> None:
    drafts = [c.validated() for c in read_seed()]

    assert [d.name for d in drafts] == EXPECTED
    assert len({d.color for d in drafts}) == len(drafts)
    assert read_rules() == {"FISCALIA GENERAL DE LA REPUBLICA": RelevanceRule.FGR_FEDERAL}


def test_cada_semilla_cabe_en_una_consulta_por_proveedor_en_un_lugar_comun() -> None:
    place = QueryPlace(("Iztapalapa",), (), MEXICO)

    for draft in (c.validated() for c in read_seed()):
        assert len(build_queries(draft, place, WEEK)) == len(Provider), draft.name


def test_con_un_nombre_oficial_largo_se_parte_sin_perder_palabras() -> None:
    # Medido: con el límite prudente de 32 palabras (VERIFICAR en F3), un
    # concepto largo en Juchitán necesita 2 consultas de SearchApi.
    place = QueryPlace(("Heroica Ciudad de Juchitán de Zaragoza",), ("Oaxaca",), MEXICO)

    for draft in (c.validated() for c in read_seed()):
        queries = [q for q in build_queries(draft, place, WEEK) if q.provider == "searchapi"]
        assert tuple(k for q in queries for k in q.keywords) == draft.keywords, draft.name
