"""Prompt ``enrich_v6`` (ADR-0114): relevancia estricta para conceptos abiertos.

Lo que se cuida aquí:

- con solo conceptos exactos (monitor FGR, temas) el texto es el de
  ``enrich_v5`` letra por letra, aunque la búsqueda traiga región y
  procedencia;
- con un concepto abierto lleva la región, la entidad obligatoria, cómo llegó
  la nota y las bandas de puntaje.
"""

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.adapters.llm.common import PROMPT_VERSION, build_prompt
from app.application.ports.llm import EnrichmentRequest
from app.domain.concept import QueryMode
from app.domain.core_terms import QueryOrigin
from app.domain.enrichment import ConceptBrief

PROMPTS = Path(__file__).parents[2] / "app" / "adapters" / "llm" / "prompts"
EXTORSION = ConceptBrief(3, "Extorsión", "Cobro de piso y amenazas", ("extorsión", "cobro de piso"))
ETERNAL = ConceptBrief(
    9,
    "hacker eternal",
    "hacker eternal",
    ("hacker eternal",),
    QueryMode.OPEN,
    ("Eternal",),
)
RSS = QueryOrigin("google_news_rss", "Google News RSS", ("hacker eternal",), True)
LOCAL = QueryOrigin("indice_local", "Índice local (GDELT + medios)", ("hacker eternal",), False)
TITLE = "Hackean Buró Laboral y exponen datos de miles de trabajadores"
TEXT = "Hackean Buró Laboral y exponen datos de miles de trabajadores"
PUBLISHED = datetime(2026, 11, 18, 15, tzinfo=UTC)
EXACT_REQUEST = EnrichmentRequest(TITLE, TEXT, PUBLISHED, [EXTORSION])
OPEN_REQUEST = EnrichmentRequest(
    TITLE,
    TEXT,
    PUBLISHED,
    [ETERNAL],
    region="Mundo",
    origins=(RSS,),
    unconfirmed_terms=("Eternal",),
)


def v5_prompt(concepts: str) -> str:
    return (
        (PROMPTS / "enrich_v5.md")
        .read_text(encoding="utf-8")
        .format(concepts=concepts, published_at="2026-11-18", title=TITLE, text=TEXT)
    )


# Revisión del 18/11/2026 (hallazgo 4): lo que se supo de Eternal por las
# notas de la búsqueda que sí lo nombran.
ETERNAL_CONTEXT = (
    "El hacker Eternal vende datos de trabajadores del Buró Laboral",
    "ETERNAL expone 746 MIL cuentas de PILLOFON y ya clonan",
)
CONTEXT_BLOCK = (
    "El título y el fragmento no nombran a «Eternal».\n"
    "Lo que se sabe de «Eternal» por otras notas de esta búsqueda que sí lo nombran:\n"
    "- El hacker Eternal vende datos de trabajadores del Buró Laboral\n"
    "- ETERNAL expone 746 MIL cuentas de PILLOFON y ya clonan\n\n"
    "Fecha de publicación: 2026-11-18"
)
NO_CONTEXT_LINE = (
    "Ninguna otra nota de esta búsqueda nombra a «Eternal»: "
    "no hay hechos con qué comparar el título."
)
EXACT_FIRST_LINE = (
    "Eres un analista que lee noticias en español para un monitor de noticias "
    "geolocalizadas sobre México. Lee la nota y responde SOLO con el JSON pedido."
)
EXTORSION_LINE = (
    "- concept_id 3: Extorsión. Cobro de piso y amenazas (palabras clave: extorsión, cobro de piso)"
)


def test_la_version_cambia_para_que_se_vuelva_a_juzgar() -> None:
    assert PROMPT_VERSION == "enrich_v6"


def test_un_concepto_exacto_recibe_el_prompt_de_v5_letra_por_letra() -> None:
    # La FGR y los temas no cambian de criterio (ADR-0109 D2, ADR-0114).
    assert build_prompt(EXACT_REQUEST) == v5_prompt(EXTORSION_LINE)


def test_un_concepto_exacto_ignora_region_y_procedencia() -> None:
    with_extras = replace(
        EXACT_REQUEST, region="Jalisco", origins=(RSS, LOCAL), unconfirmed_terms=("Eternal",)
    )

    assert build_prompt(with_extras) == v5_prompt(EXTORSION_LINE)


def test_un_concepto_abierto_sin_descripcion_tambien_sigue_igual_que_v5() -> None:
    bare = ConceptBrief(8, "Hackeos", "", ("filtran datos",), QueryMode.OPEN)

    prompt = build_prompt(replace(EXACT_REQUEST, concepts=[bare], region="Jalisco"))

    assert prompt == v5_prompt("- concept_id 8: Hackeos.  (palabras clave: filtran datos)")


def test_el_concepto_abierto_dice_donde_se_busca() -> None:
    prompt = build_prompt(OPEN_REQUEST)

    assert prompt.startswith(
        "Eres un analista que lee noticias en español para un monitor de noticias "
        "geolocalizadas. La búsqueda es en: Mundo. Lee la nota"
    )
    assert "sobre México" not in prompt
    assert "no descartes una nota por el país o el lugar donde ocurre" in prompt


def test_sin_region_no_inventa_una() -> None:
    prompt = build_prompt(replace(OPEN_REQUEST, region=None))

    assert "La búsqueda es en" not in prompt
    assert prompt.startswith(
        "Eres un analista que lee noticias en español para un monitor de noticias "
        "geolocalizadas. Lee la nota"
    )


def test_la_entidad_pedida_es_condicion() -> None:
    prompt = build_prompt(OPEN_REQUEST)

    assert (
        "- concept_id 9: hacker eternal. Lo que busca el analista: hacker eternal "
        "(frases de búsqueda, solo como pista: hacker eternal) Debe hablar de: Eternal."
    ) in prompt
    assert "Una nota del mismo tema sin esa entidad NO es relevante: es cercana" in prompt
    assert "exactamente lo que pide el analista" in prompt


def test_el_juez_ve_como_llego_la_nota() -> None:
    prompt = build_prompt(replace(OPEN_REQUEST, origins=(RSS, LOCAL)))

    assert (
        "Cómo llegó la nota:\n"
        "- Google News RSS (busca en el texto completo de las notas), con «hacker eternal».\n"
        "- Índice local (GDELT + medios) (no cuenta como buscador de texto completo), "
        "con «hacker eternal».\n"
        "El título y el fragmento no nombran a «Eternal».\n"
        f"{NO_CONTEXT_LINE}\n\n"
        "Fecha de publicación: 2026-11-18"
    ) in prompt
    assert "relevance_score de 0.65 a 0.75" in prompt
    # Sin otras notas que nombren a Eternal no hay con qué comparar el título.
    assert NO_CONTEXT_LINE in prompt


def test_sin_procedencia_no_hay_bloque() -> None:
    prompt = build_prompt(replace(OPEN_REQUEST, origins=(), unconfirmed_terms=()))

    assert "Cómo llegó la nota" not in prompt
    assert "Debe hablar de: Eternal.\n\nFecha de publicación: 2026-11-18" in prompt


def test_las_bandas_van_en_el_prompt() -> None:
    prompt = build_prompt(OPEN_REQUEST)

    for band in (
        "0.8 a 1: relevante",
        '0.6 a 0.79: relevante "por confirmar"',
        "0.3 a 0.59: no relevante, cercana",
        "0 a 0.29: no relevante, ajena",
        "is_relevant es true solo con 0.6 o más",
    ):
        assert band in prompt
    # Las alertas genéricas y las estafas de temporada no cuentan como lo pedido.
    assert "las estafas de temporada" in prompt


def test_una_busqueda_mixta_usa_las_reglas_de_los_abiertos_sin_tocar_al_exacto() -> None:
    prompt = build_prompt(replace(OPEN_REQUEST, concepts=[EXTORSION, ETERNAL]))

    assert EXTORSION_LINE in prompt
    assert "Debe hablar de: Eternal." in prompt
    assert "Cómo llegó la nota:" in prompt


def test_una_busqueda_mixta_deja_al_exacto_sobre_mexico() -> None:
    # Revisión del 18/11/2026 (hallazgo 6): la FGR en una búsqueda manual con
    # un concepto abierto seguía perdiendo «sobre México».
    prompt = build_prompt(replace(OPEN_REQUEST, concepts=[EXTORSION, ETERNAL]))

    first_line = prompt.splitlines()[0]
    assert first_line == (
        f"{EXACT_FIRST_LINE} Los conceptos que traen «Lo que busca el analista» se buscan "
        "en: Mundo."
    )
    assert "La búsqueda es en" not in prompt
    # La regla de lugar de los abiertos dice que solo vale para ellos.
    assert (
        "   - Los conceptos sin «Lo que busca el analista» se juzgan con las reglas "
        "generales, como siempre en este monitor sobre México: la regla de lugar y "
        "las bandas de arriba son solo para los que lo traen.\n"
        "   - Prueba rápida:"
    ) in prompt


def test_una_busqueda_mixta_sin_region_no_inventa_una() -> None:
    prompt = build_prompt(replace(OPEN_REQUEST, concepts=[EXTORSION, ETERNAL], region=None))

    assert prompt.splitlines()[0] == EXACT_FIRST_LINE


def test_solo_abiertos_no_lleva_la_aclaracion_de_los_exactos() -> None:
    prompt = build_prompt(OPEN_REQUEST)

    assert "Los conceptos sin «Lo que busca el analista»" not in prompt


@pytest.mark.parametrize(
    "title",
    [
        # Real: coincide con el hackeo de Eternal al Buró Laboral.
        "Revelan listas negras laborales; vende hacker datos",
        # Real (google_base.md): ruido del tema que Google trajo por «hacker eternal».
        "Ariana Grande demanda a hackers que filtraron fotos privadas",
    ],
)
def test_el_juez_ve_lo_que_se_sabe_de_la_entidad(title: str) -> None:
    request = replace(OPEN_REQUEST, title=title, text=title, entity_context=ETERNAL_CONTEXT)

    prompt = build_prompt(request)

    assert CONTEXT_BLOCK in prompt
    assert NO_CONTEXT_LINE not in prompt


def test_por_confirmar_solo_si_el_titulo_coincide_con_un_hecho_de_la_entidad() -> None:
    prompt = build_prompt(replace(OPEN_REQUEST, entity_context=ETERNAL_CONTEXT))

    assert (
        'márcala relevante "por confirmar", con relevance_score de 0.65 a 0.75, solo si '
        "el título coincide con un hecho concreto de lo que se sabe de la entidad"
    ) in prompt
    assert "es cercana, con relevance_score de 0.35 a 0.5" in prompt
    assert (
        '"El título no nombra a Eternal y no coincide con lo que se sabe de Eternal."'
    ) in prompt
    assert '"Revelan listas negras laborales; vende hacker datos"' in prompt
    assert '"Ariana Grande demanda a hackers"' in prompt
    # Ya no basta con que el título sea «coherente con el tema».
    assert "el título es coherente con el tema pedido" not in prompt


def test_la_regla_de_la_entidad_remite_a_la_excepcion_de_procedencia() -> None:
    # Antes «sin esa entidad NO es relevante» chocaba con «por confirmar» y no
    # se sabía cuál ganaba.
    prompt = build_prompt(OPEN_REQUEST)

    assert (
        "Una nota del mismo tema sin esa entidad NO es relevante: es cercana (un "
        'ciberataque de otro grupo no sirve para "hacker Eternal"). La única excepción '
        "es la de procedencia, más abajo."
    ) in prompt


def test_el_contexto_no_llega_a_los_exactos() -> None:
    with_context = replace(EXACT_REQUEST, entity_context=ETERNAL_CONTEXT)

    assert build_prompt(with_context) == v5_prompt(EXTORSION_LINE)
