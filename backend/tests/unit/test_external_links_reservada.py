"""``external_links`` está reservada: ninguna lógica la lee ni la escribe (ADR-0101).

La tabla existe desde la migración 0018 como enchufe futuro hacia registros de
otras bases del sistema Oráculo, y la Fase 9 no la usa. Esta prueba lo vuelve
una regla que se revisa sola: si algún archivo de ``app/`` la nombra, falla,
y conectarla obliga a cambiar el ADR primero.
"""

from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[2] / "app"


def test_ningun_archivo_de_la_aplicacion_usa_external_links() -> None:
    users = [
        path.relative_to(APP_DIR).as_posix()
        for path in APP_DIR.rglob("*.py")
        if "external_links" in path.read_text(encoding="utf-8")
    ]

    assert users == [], f"external_links está reservada (ADR-0101) y la usan: {users}"
