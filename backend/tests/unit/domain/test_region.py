"""Entidad Region: nombre para mostrar, profundidad y migas de pan."""

from app.domain.region import RegionDetail, RegionLevel
from tests.unit.fake_regions import CDMX, IZTAPALAPA, MEXICO, make_region


def test_municipios_y_localidades_muestran_su_prefijo() -> None:
    assert IZTAPALAPA.display_name == "Alcaldía Iztapalapa"
    localidad = make_region(9, "La Cañada", RegionLevel.LOCALITY, prefix="Localidad")
    assert localidad.display_name == "Localidad La Cañada"


def test_paises_y_estados_se_muestran_solo_con_su_nombre() -> None:
    assert MEXICO.display_name == "México"
    assert CDMX.display_name == "Ciudad de México"


def test_profundidad_de_cada_nivel() -> None:
    assert [level.depth for level in RegionLevel] == [0, 1, 2, 3]


def test_migas_de_pan_del_mas_general_al_mas_cercano() -> None:
    detail = RegionDetail(IZTAPALAPA, (MEXICO.ref(), CDMX.ref()))

    assert detail.breadcrumb == "México › Ciudad de México › Iztapalapa"


def test_referencia_corta() -> None:
    ref = IZTAPALAPA.ref()

    assert (ref.id, ref.level, ref.code, ref.name) == (
        3,
        RegionLevel.MUNICIPALITY,
        "09007",
        "Iztapalapa",
    )
