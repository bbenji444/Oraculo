"""Filtro de palabras del pedido (ADR-0114): entidad estricta, tema laxo, procedencia."""

import pytest

from app.adapters.providers.searchapi_web import SECTIONS
from app.domain.core_terms import (
    MAX_CONTEXT_CHARS,
    MAX_CONTEXT_FRAGMENTS,
    STOPWORDS,
    WEB_ORGANIC_SECTION,
    WEB_SECTION_LABELS,
    CoreMatcher,
    CoreTerms,
    CoreVerdict,
    QueryOrigin,
    _text_norm,
    core_terms_for,
    stem,
    term_aliases,
    theme_roots,
)
from app.domain.news_index import index_text_norm
from app.domain.queries import FULL_TEXT_PROVIDERS, Provider

# Los títulos reales que Google News RSS trajo por «hacker eternal» (VM,
# búsquedas 35 y 36 del 18/11/2026): ninguno dice «Eternal».
BURO = "Hackean Buró Laboral y exponen datos de miles de trabajadores"
PILLOFON = "Hackean 746 mil cuentas de celular, incluidas las de Pillofon"
RSS_ETERNAL = QueryOrigin("google_news_rss", "Google News RSS", ("hacker eternal",), True)
WEB_ETERNAL = QueryOrigin("searchapi_web", "Google web", ("Hacker Eternal",), True)
LOCAL_ETERNAL = QueryOrigin("indice_local", "Índice local", ("hacker eternal",), False)
RSS_OTHER = QueryOrigin("google_news_rss", "Google News RSS", ("hackeo bases de datos",), True)
LOCAL_OTHER = QueryOrigin("indice_local", "Índice local", ("roban vehículos",), False)
ETERNAL = CoreTerms(("Eternal",), ("HACK",))


@pytest.mark.parametrize(
    ("words", "root"),
    [
        (("ROBO", "ROBOS", "ROBAN", "ROBARON", "ROBADO", "ROBA", "ROBAR"), "ROB"),
        (("AUTO", "AUTOS"), "AUT"),
        (("HACKER", "HACKERS", "HACKEO", "HACKEOS", "HACKEAN", "HACKEADAS", "HACKEAR"), "HACK"),
        (("VEHICULO", "VEHICULOS", "VEHICULAR"), "VEHICUL"),
        (("FILTRAN", "FILTRACION", "FILTRACIONES", "FILTRADOS"), "FILTR"),
        (("CAMION", "CAMIONES"), "CAMION"),
        (("SECUESTRO", "SECUESTRAN", "SECUESTRADORES"), "SECUESTR"),
    ],
)
def test_las_formas_de_una_palabra_quedan_en_la_misma_raiz(
    words: tuple[str, ...], root: str
) -> None:
    assert {stem(w) for w in words} == {root}


@pytest.mark.parametrize(
    ("word", "not_root"),
    [
        # El problema de cortar por el inicio: ROB empataría con Roberto y robot.
        ("ROBERTO", "ROB"),
        ("ROBOT", "ROB"),
        ("ROBOTS", "ROB"),
        ("ROBLES", "ROB"),
        # Y AUTO con autoridad, autor o automóvil.
        ("AUTORIDAD", "AUT"),
        ("AUTORIDADES", "AUT"),
        ("AUTOR", "AUT"),
        ("AUTORES", "AUT"),
        ("AUTOMOVIL", "AUT"),
        ("AUTONOMA", "AUT"),
    ],
)
def test_el_recorte_no_empata_palabras_que_solo_empiezan_igual(word: str, not_root: str) -> None:
    assert stem(word) != not_root


def test_el_recorte_no_deja_raices_de_menos_de_tres_letras() -> None:
    assert stem("RED") == "RED"
    assert stem("REDES") == "RED"
    assert stem("MES") == "MES"


def test_raices_sin_palabras_vacias_ni_lugar_ni_numeros() -> None:
    roots = theme_roots(["robo de vehículos en Jalisco", "roban 3 camionetas"], ["Jalisco"])

    assert roots == ("ROB", "VEHICUL", "CAMIONET")


def test_las_palabras_de_todo_el_mundo_y_del_tiempo_no_son_tema() -> None:
    assert theme_roots(["bases de datos hackeadas en todo el mundo esta semana"]) == (
        "BAS",
        "DAT",
        "HACK",
    )
    assert {"MUNDO", "SEMANA", "NOTICIAS"} <= STOPWORDS


def test_pedido_de_una_entidad_con_tema() -> None:
    core = core_terms_for(
        "hacker eternal en todo el mundo",
        ["hacker eternal", "Eternal filtra datos"],
        ["eternal"],
        ["Mundo"],
    )

    assert core == CoreTerms(("eternal",), ("HACK", "FILTR", "DAT"))


def test_si_solo_escribio_un_nombre_no_se_exige_tema() -> None:
    # Las frases de la IA («LockBit ataque») agregan tema que nadie pidió y
    # tirarían «Detienen al líder de LockBit».
    core = core_terms_for(
        "LockBit en Jalisco", ["LockBit", "LockBit ataque"], ["LockBit"], ["Jalisco"]
    )

    assert core == CoreTerms(("LockBit",), ())
    verdict = CoreMatcher(core).check("Detienen al líder de LockBit", None, LOCAL_ETERNAL)
    assert verdict is CoreVerdict.CONFIRMED


def test_sin_entidades_ni_palabras_de_contenido_no_hay_filtro() -> None:
    assert core_terms_for("de la semana", ["las de hoy"], [], []) is None


def test_eternal_en_el_titulo_pasa_confirmada() -> None:
    title = "El hacker Eternal vuelve a atacar al IMSS"

    assert CoreMatcher(ETERNAL).check(title, None, LOCAL_ETERNAL) is CoreVerdict.CONFIRMED


def test_eternal_en_el_fragmento_tambien_cuenta() -> None:
    verdict = CoreMatcher(ETERNAL).check(BURO, "El grupo Eternal publicó la base.", LOCAL_ETERNAL)

    assert verdict is CoreVerdict.CONFIRMED


@pytest.mark.parametrize("origin", [RSS_ETERNAL, WEB_ETERNAL])
def test_sin_eternal_en_el_titulo_pasa_por_procedencia(origin: QueryOrigin) -> None:
    # Google News RSS exige todas las palabras de la consulta en la nota: si
    # la trajo «hacker eternal», Eternal está en el cuerpo (ADR-0109).
    matcher = CoreMatcher(ETERNAL)

    assert matcher.check(BURO, None, origin) is CoreVerdict.UNCONFIRMED
    assert matcher.check(PILLOFON, None, origin) is CoreVerdict.UNCONFIRMED
    assert matcher.missing_terms(BURO, None) == ("Eternal",)


def test_sin_eternal_y_de_un_buscador_de_titulos_se_descarta() -> None:
    assert CoreMatcher(ETERNAL).check(BURO, None, LOCAL_ETERNAL) is CoreVerdict.NO_ENTITY


def test_sin_eternal_y_de_una_consulta_sin_eternal_se_descarta() -> None:
    assert CoreMatcher(ETERNAL).check(BURO, None, RSS_OTHER) is CoreVerdict.NO_ENTITY


def test_eternal_sin_el_tema_se_descarta_si_no_lo_trajo_google() -> None:
    # «Eternal» también es una película: sin nada de hackeo, en un buscador de
    # títulos (índice local), no es lo pedido.
    verdict = CoreMatcher(ETERNAL).check("Eternal Sunshine vuelve a los cines", None, LOCAL_ETERNAL)

    assert verdict is CoreVerdict.OFF_THEME
    assert not verdict.kept


def test_eternal_sin_el_tema_pasa_al_juez_si_lo_trajo_google() -> None:
    # Revisión del 18/11/2026 (hallazgo 2): Google ya exigió las palabras en el
    # cuerpo; que decida el juez y la banda «ajena» lo esconde.
    verdict = CoreMatcher(ETERNAL).check("Eternal Sunshine vuelve a los cines", None, RSS_ETERNAL)

    assert verdict is CoreVerdict.CONFIRMED


def test_robo_de_vehiculos_en_jalisco() -> None:
    # 789b2553 (VM, 18/11/2026): «roban vehículos Jalisco» trajo esto.
    core = core_terms_for(
        "roban vehículos en Jalisco", ["roban vehículos", "robo de camioneta"], [], ["Jalisco"]
    )
    assert core is not None
    matcher = CoreMatcher(core)

    # En el índice local (solo título y resumen) el tema se exige.
    assert matcher.check("Concentración feminista en Guadalajara", None, LOCAL_OTHER) is (
        CoreVerdict.OFF_THEME
    )
    assert matcher.check("Cancelan vuelos desde Guadalajara", None, LOCAL_OTHER) is (
        CoreVerdict.OFF_THEME
    )
    assert matcher.check("Roban camioneta con violencia en Zapopan", None, LOCAL_OTHER) is (
        CoreVerdict.CONFIRMED
    )
    assert matcher.check("Detienen a ladrones de vehículos en Tlaquepaque", None, LOCAL_OTHER) is (
        CoreVerdict.CONFIRMED
    )
    # Lo que trajo Google News RSS pasa al juez (hallazgo 2 de la revisión del
    # 18/11/2026): la banda «ajena» lo esconde en pantalla.
    assert matcher.check("Concentración feminista en Guadalajara", None, RSS_OTHER).kept


def test_roberto_y_las_autoridades_no_son_robo_de_autos() -> None:
    core = core_terms_for("robo de autos", ["robo de autos"], [], [])
    assert core == CoreTerms((), ("ROB", "AUT"))
    matcher = CoreMatcher(core)

    assert not matcher.on_theme("Roberto Gómez gana la elección", None)
    assert not matcher.on_theme("Autoridades de Jalisco presentan su informe", None)
    assert not matcher.on_theme("Un robot atiende en el aeropuerto", None)
    assert matcher.on_theme("Le robaron el auto afuera de su casa", None)


def test_una_entidad_de_varias_palabras_va_completa() -> None:
    matcher = CoreMatcher(CoreTerms(("Cártel de Sinaloa",), ()))

    assert matcher.missing_terms("Detienen a operador del Cartel de Sinaloa", None) == ()
    assert matcher.missing_terms("Detienen a operador de Sinaloa", None) == ("Cártel de Sinaloa",)


def test_un_nombre_de_persona_cuenta_con_su_apellido() -> None:
    # Prueba real del 18/11/2026: los títulos dicen «Harfuch» o «García
    # Harfuch» y el juez leía «el título no nombra a Omar García Harfuch».
    matcher = CoreMatcher(CoreTerms(("Omar García Harfuch",), ()))

    assert matcher.missing_terms("Harfuch confirma la captura de El Topo", None) == ()
    assert matcher.missing_terms("Anuncia García Harfuch captura de El Topo", None) == ()
    assert matcher.missing_terms("Capturan a El Topo en Zapopan", None) == ("Omar García Harfuch",)
    # Del índice local ya no se tira por decir solo el apellido.
    assert matcher.check("Harfuch se reúne con gobernadores", None, LOCAL_ETERNAL).kept


@pytest.mark.parametrize(
    ("term", "forms"),
    [
        ("Omar García Harfuch", ("OMAR GARCIA HARFUCH", "HARFUCH", "OGH")),
        ("Luisito Comunica", ("LUISITO COMUNICA", "COMUNICA")),
        ("Eternal", ("ETERNAL",)),
        # Con 4 palabras o más ya no es seguro que la última sea un apellido.
        ("Andrés Manuel López Obrador", ("ANDRES MANUEL LOPEZ OBRADOR", "AMLO")),
        # Con palabras de enlace es una institución o un alias: va completo
        # o con su sigla.
        ("Fiscalía General de la República", ("FISCALIA GENERAL DE LA REPUBLICA", "FGR")),
        ("Cártel Jalisco Nueva Generación", ("CARTEL JALISCO NUEVA GENERACION", "CJNG")),
        ("Cártel de Sinaloa", ("CARTEL DE SINALOA",)),
        ("Los Deltas", ("LOS DELTAS",)),
        ("El Mencho", ("EL MENCHO",)),
        # Un apellido corto es una palabra común: va completo.
        ("Octavio Paz", ("OCTAVIO PAZ",)),
        # Una sigla que se lee como palabra común («más») no cuenta.
        ("Mesa Ampliada de Seguridad", ("MESA AMPLIADA DE SEGURIDAD",)),
    ],
)
def test_formas_de_un_termino_obligatorio(term: str, forms: tuple[str, ...]) -> None:
    assert term_aliases(term) == forms


def test_una_institucion_cuenta_con_su_sigla() -> None:
    # Prueba real del 18/11/2026 («cateo de la Fiscalía General de la
    # República», 1 día): los títulos dicen «FGR» y se tiraron 90 notas
    # antes de la IA; «FGR asegura 2 predios… en Balancán» quedó cercana.
    matcher = CoreMatcher(CoreTerms(("Fiscalía General de la República",), ()))

    assert matcher.missing_terms("FGR asegura 2 predios por tala ilegal en Balancán", None) == ()
    assert matcher.missing_terms("Asegura FGE 40 kg de droga en Monclova", None) == (
        "Fiscalía General de la República",
    )


def test_la_entidad_va_como_palabra_completa() -> None:
    matcher = CoreMatcher(CoreTerms(("Eternal",), ()))

    assert matcher.missing_terms("Eternals, la película de Marvel", None) == ("Eternal",)


def test_la_procedencia_solo_cuenta_en_buscadores_de_texto_completo() -> None:
    assert RSS_ETERNAL.carries("Eternal")
    assert not LOCAL_ETERNAL.carries("Eternal")
    assert not RSS_OTHER.carries("Eternal")


def test_los_buscadores_de_texto_completo_son_los_del_contrato() -> None:
    assert frozenset({"google_news_rss", "searchapi", "searchapi_web"}) == {
        p.value for p in FULL_TEXT_PROVIDERS
    }
    assert Provider.LOCAL_INDEX not in FULL_TEXT_PROVIDERS


def test_el_texto_normalizado_es_el_del_indice_local() -> None:
    title, snippet = "Hackean al  IMSS-NL: Peñón", "Fragmento con acentos: ataqué"

    assert _text_norm(title, snippet) == index_text_norm(title, snippet)
    assert _text_norm(title, None) == index_text_norm(title, None)


# --- Procedencia por nota (revisión del 18/11/2026: hallazgo 2 y R1-3) ---

# Google web: los resultados orgánicos buscan en el texto completo; los
# carruseles (videos, shorts, tweets, noticias destacadas) no.
WEB_ORGANIC = QueryOrigin(
    "searchapi_web", "Google web", ("hacker eternal",), True, WEB_ORGANIC_SECTION
)
WEB_VIDEOS = QueryOrigin("searchapi_web", "Google web", ("hacker eternal",), False, "inline_videos")


@pytest.mark.parametrize(
    "title",
    [
        # Títulos reales de la base de desarrollo (revisión, rv25_sim.py): salían
        # off_theme porque HUACHICOL no empata con «hidrocarburo» ni
        # «combustible», y HUACHICOLEROS queda en HUACHICOLER.
        "Aseguran 2 mil 500 litros de hidrocarburo y camioneta en Tlahuelilpan",
        "Localizan 2 mil 500 litros de combustible en inmueble de Tlahuelilpan, Hidalgo",
        "Detienen a tres huachicoleros en Tula",
    ],
)
def test_huachicol_en_hidalgo_lo_que_trajo_google_llega_al_juez(title: str) -> None:
    core = core_terms_for("huachicol en Hidalgo", ["huachicol"], [], ["Hidalgo"])
    assert core is not None
    rss = QueryOrigin("google_news_rss", "Google News RSS", ("huachicol",), True)

    assert CoreMatcher(core).check(title, None, rss) is CoreVerdict.CONFIRMED


def test_huachicol_del_indice_local_sin_la_raiz_sigue_fuera() -> None:
    core = core_terms_for("huachicol en Hidalgo", ["huachicol"], [], ["Hidalgo"])
    assert core is not None
    local = QueryOrigin("indice_local", "Índice local", ("huachicol",), False)
    title = "Aseguran 2 mil 500 litros de hidrocarburo y camioneta en Tlahuelilpan"

    assert CoreMatcher(core).check(title, None, local) is CoreVerdict.OFF_THEME


def test_desaparecidos_en_jalisco_el_rancho_izaguirre_llega_al_juez() -> None:
    # DESAPARICIONES queda en DESAPARI y DESAPARECIDOS en DESAPAREC.
    title = (
        "DIPUTADAS Y DIPUTADOS CUESTIONAN AL FISCAL DE JALISCO SOBRE DETENCIONES, "
        "DESAPARICIONES Y EL CASO DEL RANCHO IZAGUIRRE"
    )
    core = core_terms_for(
        "desaparecidos en Jalisco",
        ["desaparecidos Jalisco", "buscan desaparecidos"],
        [],
        ["Jalisco"],
    )
    assert core is not None
    rss = QueryOrigin("google_news_rss", "Google News RSS", ("desaparecidos Jalisco",), True)
    local = QueryOrigin("indice_local", "Índice local", ("desaparecidos Jalisco",), False)

    assert CoreMatcher(core).check(title, None, rss) is CoreVerdict.CONFIRMED
    assert CoreMatcher(core).check(title, None, local) is CoreVerdict.OFF_THEME


@pytest.mark.parametrize(
    ("title", "channel", "verdict"),
    [
        # Los 4 inline_videos del fixture real (searchapi_web_hacker_eternal_7d).
        (
            "ETERNAL expone 746 MIL cuentas de PILLOFON y ya clonan",
            "YouTube · La Saga",
            CoreVerdict.CONFIRMED,
        ),
        (
            "Hackers logran afectar a casi 200 empresas y medios de",
            "YouTube · UnoTV",
            CoreVerdict.NO_ENTITY,
        ),
        ("NSA internal network outage reported", "YouTube · NMás", CoreVerdict.NO_ENTITY),
        (
            "CIBERATAQUE afecta a las webs de IKEA, ZOOM y otras",
            "YouTube · 20minutos",
            CoreVerdict.NO_ENTITY,
        ),
    ],
)
def test_los_videos_de_google_web_necesitan_la_entidad(
    title: str, channel: str, verdict: CoreVerdict
) -> None:
    # Antes, La Saga salía off_theme (su título no trae HACK) y el genérico
    # de UnoTV pasaba «por confirmar»: el carrusel no busca en el texto completo.
    assert CoreMatcher(ETERNAL).check(title, None, WEB_VIDEOS, channel) is verdict


def test_en_un_carrusel_cuentan_el_canal_y_el_autor() -> None:
    verdict = CoreMatcher(ETERNAL).check("Nuevo video", None, WEB_VIDEOS, "YouTube · Eternal Leaks")

    assert verdict is CoreVerdict.CONFIRMED


def test_un_carrusel_sin_entidad_que_exigir_si_pide_el_tema() -> None:
    core = CoreTerms((), ("HACK",))
    stories = QueryOrigin("searchapi_web", "Google web", ("hackeos",), False, "top_stories")

    assert CoreMatcher(core).check("Gana el América", None, stories) is CoreVerdict.OFF_THEME
    assert CoreMatcher(core).check("Hackean al SAT", None, stories) is CoreVerdict.CONFIRMED


def test_los_organicos_de_google_web_cuentan_como_texto_completo() -> None:
    matcher = CoreMatcher(ETERNAL)

    assert matcher.check(BURO, None, WEB_ORGANIC) is CoreVerdict.UNCONFIRMED
    assert WEB_ORGANIC.carries("Eternal")
    assert not WEB_VIDEOS.carries("Eternal")
    assert WEB_VIDEOS.carousel
    assert not WEB_ORGANIC.carousel
    assert not RSS_ETERNAL.carousel


def test_las_secciones_de_carrusel_son_las_del_adaptador() -> None:
    # El adaptador las pone en raw["section"]; si cambia un nombre, la regla
    # de procedencia dejaría de reconocerla.
    assert {WEB_ORGANIC_SECTION, *WEB_SECTION_LABELS} <= set(SECTIONS)
    assert WEB_ORGANIC_SECTION not in WEB_SECTION_LABELS


# Lo que se supo de Eternal en la búsqueda real del 18/11/2026: títulos de
# Google News y Google web que sí lo nombran (revisión, hallazgo 4).
ETERNAL_NOTES: list[tuple[str, str | None]] = [
    ("El hacker Eternal vende datos de trabajadores del Buró Laboral", None),
    (
        "ETERNAL expone 746 MIL cuentas de PILLOFON y ya clonan",
        "El hacker Eternal ofrece 746 mil cuentas de celular a la venta.",
    ),
    # No nombra a Eternal: no cuenta como algo que se sepa de él.
    (BURO, None),
    # La misma nota de otro medio no repite el hecho.
    ("El hacker Eternal vende datos de trabajadores del Buró Laboral", "Otro medio."),
]


def test_el_contexto_de_la_entidad_sale_de_las_notas_que_la_nombran() -> None:
    context = CoreMatcher(ETERNAL).entity_context(ETERNAL_NOTES, ("Eternal",))

    assert context == (
        "El hacker Eternal vende datos de trabajadores del Buró Laboral",
        "ETERNAL expone 746 MIL cuentas de PILLOFON y ya clonan — "
        "El hacker Eternal ofrece 746 mil cuentas de celular a la venta.",
    )


def test_el_contexto_tiene_tope_de_fragmentos_y_de_largo() -> None:
    long_snippet = "El hacker publicó una muestra de la base " * 10
    notes = [(f"Eternal filtra la base número {i}", long_snippet) for i in range(10)]

    context = CoreMatcher(ETERNAL).entity_context(notes, ("Eternal",))

    assert len(context) == MAX_CONTEXT_FRAGMENTS
    assert all(len(fragment) <= MAX_CONTEXT_CHARS for fragment in context)
    assert context[0].startswith("Eternal filtra la base número 0 — El hacker publicó")
    assert context[0].endswith("…")


def test_sin_entidad_que_buscar_no_hay_contexto() -> None:
    assert CoreMatcher(ETERNAL).entity_context(ETERNAL_NOTES, ()) == ()
    no_entity = CoreMatcher(CoreTerms((), ("HACK",)))
    assert no_entity.entity_context(ETERNAL_NOTES, ("Eternal",)) == ()
