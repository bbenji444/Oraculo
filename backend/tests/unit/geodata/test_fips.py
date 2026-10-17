"""Equivalencias FIPS (GDELT) → INEGI."""

from pathlib import Path

import pytest

from app.geodata.fips import FipsTableError, read_fips_to_inegi


def test_la_tabla_real_cubre_los_32_estados_de_ida_y_vuelta() -> None:
    mapping = read_fips_to_inegi()

    assert len(mapping) == 32
    assert sorted(mapping.values()) == [f"{n:02d}" for n in range(1, 33)]


@pytest.mark.parametrize(
    ("fips", "inegi"),
    [
        # Los cuatro que no coinciden (confirmados con la muestra real salvo Colima).
        ("MX07", "05"),  # Coahuila
        ("MX05", "07"),  # Chiapas
        ("MX06", "08"),  # Chihuahua
        ("MX08", "06"),  # Colima
        # Algunos que sí coinciden.
        ("MX09", "09"),  # Ciudad de México
        ("MX15", "15"),  # México
        ("MX21", "21"),  # Puebla
    ],
)
def test_equivalencias(fips: str, inegi: str) -> None:
    assert read_fips_to_inegi()[fips] == inegi


def test_tabla_incompleta_es_error(tmp_path: Path) -> None:
    path = tmp_path / "fips.csv"
    path.write_text("fips,inegi,estado,verificado\nMX01,01,Aguascalientes,x\n", encoding="utf-8")

    with pytest.raises(FipsTableError, match="32"):
        read_fips_to_inegi(path)
