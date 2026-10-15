"""Lectura cruda de DBF y detección de encoding con bytes reales (CLAUDE.md §6.4)."""

from pathlib import Path

import pytest

from app.geodata import dbf
from app.geodata.encoding import detect_encoding, normalize_encoding_name, score_candidate
from tests.unit.geodata.dbf_builder import write_dbf

NAMES = ["Peñón de los Baños", "Nezahualcóyotl", "Acuña", "Güémez", "Tepezalá"]


def test_lee_campos_y_bytes_crudos_sin_decodificar(tmp_path: Path) -> None:
    path = tmp_path / "00mun.dbf"
    write_dbf(
        path,
        [("CVEGEO", 5), ("NOMGEO", 40)],
        [[b"09007", b"Iztapalapa"], [b"15058", "Nezahualcóyotl".encode()]],
    )

    header = dbf.read_header(path)
    rows = list(dbf.iter_raw_values(path, ("NOMGEO", "CVEGEO")))

    assert header.record_count == 2
    assert [f.name for f in header.fields] == ["CVEGEO", "NOMGEO"]
    assert rows == [
        (b"Iztapalapa", b"09007"),
        ("Nezahualcóyotl".encode(), b"15058"),
    ]


def test_omite_registros_borrados(tmp_path: Path) -> None:
    path = tmp_path / "x.dbf"
    write_dbf(path, [("NOMGEO", 10)], [[b"uno"], [b"dos"], [b"tres"]], deleted=[1])

    assert list(dbf.iter_raw_values(path, ("NOMGEO",))) == [(b"uno",), (b"tres",)]


def test_campo_inexistente_lista_los_disponibles(tmp_path: Path) -> None:
    path = tmp_path / "x.dbf"
    write_dbf(path, [("CVEGEO", 5)], [[b"09"]])

    with pytest.raises(dbf.DbfError, match="Campos: CVEGEO"):
        list(dbf.iter_raw_values(path, ("NOMGEO",)))


def test_archivo_demasiado_corto(tmp_path: Path) -> None:
    path = tmp_path / "x.dbf"
    path.write_bytes(b"\x03abc")

    with pytest.raises(dbf.DbfError, match="demasiado corto"):
        dbf.read_header(path)


@pytest.mark.parametrize("encoding", ["utf-8", "cp1252", "cp850"])
def test_detecta_el_encoding_real_de_nombres_mexicanos(encoding: str) -> None:
    raw = [name.encode(encoding) for name in NAMES]

    report = detect_encoding(raw)

    assert report.chosen == encoding
    assert [n.decode(report.chosen) for n in raw] == NAMES


def test_cp1252_y_latin1_empatan_y_gana_el_primero_de_la_lista() -> None:
    # Para á é í ó ú ñ, cp1252 y latin1 usan los mismos bytes: el orden decide.
    assert detect_encoding([n.encode("latin1") for n in NAMES]).chosen == "cp1252"


def test_utf8_leido_como_latin1_se_detecta_como_basura() -> None:
    score = score_candidate(["Peñón".encode()], "latin1")

    assert score.decodes
    assert score.suspicious > 0
    assert score.score < 0


def test_solo_ascii_elige_utf8() -> None:
    assert detect_encoding([b"Iztapalapa", b"Toluca"]).chosen == "utf-8"


def test_reporta_si_coincide_con_lo_declarado_en_el_cpg() -> None:
    raw = [n.encode() for n in NAMES]

    assert detect_encoding(raw, declared="UTF-8").agrees_with_declared is True
    assert detect_encoding(raw, declared="1252").agrees_with_declared is False
    assert detect_encoding(raw).agrees_with_declared is None


@pytest.mark.parametrize(
    ("name", "canonical"),
    [("UTF-8", "utf-8"), ("utf8", "utf-8"), ("1252", "cp1252"), ("ISO-8859-1", "latin1")],
)
def test_normaliza_nombres_de_encoding(name: str, canonical: str) -> None:
    assert normalize_encoding_name(name) == canonical
