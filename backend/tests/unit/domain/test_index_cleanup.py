"""Qué sobra en el índice local (F12.1b, ADR-0025), con casos reales del 24/10/2026."""

from datetime import UTC, datetime, timedelta

from app.domain.dedupe import canonical_url, url_hash
from app.domain.index_cleanup import IndexKey, plan_index_cleanup

NOON = datetime(2026, 10, 16, 18, 0, tzinfo=UTC)


def key(
    note_id: int,
    url: str,
    title: str = "Huracán Trudy sigue en categoría 1",
    *,
    published: datetime = NOON,
    body: str | None = None,
    stored_hash: str | None = None,
) -> IndexKey:
    return IndexKey(
        note_id=note_id,
        url=url,
        url_hash=stored_hash or url_hash(canonical_url(url)),
        title=title,
        source_domain=canonical_url(url).split("/")[2],
        text_norm=title.upper(),
        published_at=published,
        has_body=body is not None,
        body_fingerprint=body,
    )


def test_titulo_sin_letras_sobra_sin_reemplazo() -> None:
    plan = plan_index_cleanup([key(217, "https://tiempo.com.mx/local/ichife", "🎦")])

    assert [(r.note.note_id, r.reason, r.kept) for r in plan.removals] == [
        (217, "sin_letras", None)
    ]


def test_misma_url_con_puerto_se_queda_la_que_tiene_cuerpo() -> None:
    raw = "https://razon.com.mx:443/mexico/trudy"
    plan = plan_index_cleanup(
        [
            key(1, raw, stored_hash="hash-de-la-url-cruda"),
            key(2, "https://www.razon.com.mx/mexico/trudy", body="frases"),
        ]
    )

    [removal] = plan.removals
    assert (removal.note.note_id, removal.reason) == (1, "misma_url")
    assert removal.kept is not None
    assert removal.kept.note_id == 2


def test_mismo_medio_mismo_texto_y_cuerpo_se_queda_la_mas_antigua() -> None:
    plan = plan_index_cleanup(
        [
            key(8, "https://puentelibre.mx/local/choque", body="b"),
            key(
                9,
                "https://puentelibre.mx/local%20/choque",
                published=NOON + timedelta(hours=6),
                body="b",
            ),
        ]
    )

    assert [(r.note.note_id, r.reason) for r in plan.removals] == [(9, "mismo_medio")]


def test_mismo_titulo_de_portada_con_cuerpo_distinto_no_se_junta() -> None:
    # Real: dos artículos de ciudadccs.info con el título de la portada.
    plan = plan_index_cleanup(
        [
            key(
                239,
                "https://ciudadccs.info/publicacion/52005",
                "Inicio | Periódico CiudadCCS",
                body="x",
            ),
            key(
                36976,
                "https://ciudadccs.info/publicacion/3452",
                "Inicio | Periódico CiudadCCS",
                body="y",
            ),
        ]
    )

    assert plan.removals == []


def test_otro_medio_o_fuera_de_la_ventana_no_sobra() -> None:
    plan = plan_index_cleanup(
        [
            key(1, "https://puentelibre.mx/a"),
            # Sindicada: el mismo texto en otro medio es otra fuente.
            key(2, "https://tiempo.com.mx/a"),
            # Mismo medio y texto una semana después: otra nota.
            key(3, "https://puentelibre.mx/b", published=NOON + timedelta(days=7)),
        ]
    )

    assert plan.removals == []


def test_la_ventana_se_encadena() -> None:
    # 0, +2 y +4 días: cada una está a 2 días de la anterior, es un solo tramo.
    plan = plan_index_cleanup(
        [
            key(1, "https://medio.mx/a"),
            key(2, "https://medio.mx/b", published=NOON + timedelta(days=2)),
            key(3, "https://medio.mx/c", published=NOON + timedelta(days=4)),
        ]
    )

    assert [r.note.note_id for r in plan.removals] == [2, 3]


def test_recalcula_la_huella_solo_de_las_que_se_quedan() -> None:
    plan = plan_index_cleanup(
        [
            key(1, "https://www.medio.mx/a", stored_hash="cruda-1"),
            key(2, "https://medio.mx:443/a", stored_hash="cruda-2"),
            key(3, "https://medio.mx/b", "Otra nota"),
        ]
    )

    assert plan.rehash == [(1, url_hash("https://medio.mx/a"))]
