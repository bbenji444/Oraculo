"""Descarga de geodatos con un servidor simulado en memoria (sin internet)."""

import io
import json
import os
import urllib.error
import zipfile
from email.message import Message
from pathlib import Path

import pytest

from app.geodata import descarga, descargar
from app.geodata.fuentes import Source

URL = "https://ejemplo.test/nacional.zip"
INNER_NAME = "MG_Integrado.zip"


def make_inner_zip() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as inner:
        inner.writestr("conjunto_de_datos/00ent.dbf", "Peñón de los Baños".encode("cp1252") * 50)
    return buffer.getvalue()


def make_outer_zip(inner: bytes, compression: int = zipfile.ZIP_DEFLATED) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as outer:
        # Un archivo grande e incompresible antes del buscado: si el código
        # bajara todo el ZIP, se notaría en los bytes pedidos.
        outer.writestr("01_aguascalientes.zip", os.urandom(300_000), zipfile.ZIP_STORED)
        outer.writestr(INNER_NAME, inner, compression)
    return buffer.getvalue()


class FakeServer:
    """Simula un servidor HTTP que acepta Range y cuenta lo que se pidió."""

    def __init__(self, content: bytes) -> None:
        self.content = content
        self.bytes_served = 0

    def fetch_range(self, url: str, start: int, end: int) -> bytes:
        assert url == URL
        data = self.content[start : end + 1]
        self.bytes_served += len(data)
        return data

    def fetch_size(self, url: str) -> int:
        return len(self.content)


@pytest.mark.parametrize("compression", [zipfile.ZIP_DEFLATED, zipfile.ZIP_STORED])
def test_baja_solo_el_archivo_buscado_y_queda_identico(tmp_path: Path, compression: int) -> None:
    inner = make_inner_zip()
    server = FakeServer(make_outer_zip(inner, compression))

    location = descarga.locate_member(URL, INNER_NAME, server.fetch_range, server.fetch_size)
    written = descarga.download_member(
        URL, location, tmp_path / "out.zip", server.fetch_range, chunk_bytes=1000
    )

    assert written == len(inner)
    assert (tmp_path / "out.zip").read_bytes() == inner
    # Se bajó mucho menos que el ZIP completo (que incluye 300 KB ajenos).
    assert server.bytes_served < len(server.content) // 2
    assert not (tmp_path / "out.zip.part").exists()


def test_archivo_inexistente_lista_los_disponibles() -> None:
    server = FakeServer(make_outer_zip(make_inner_zip()))

    with pytest.raises(descarga.GeodataDownloadError, match=r"01_aguascalientes\.zip"):
        descarga.locate_member(URL, "no-existe.zip", server.fetch_range, server.fetch_size)


def test_datos_danados_no_dejan_archivo_final(tmp_path: Path) -> None:
    server = FakeServer(make_outer_zip(make_inner_zip(), zipfile.ZIP_STORED))
    location = descarga.locate_member(URL, INNER_NAME, server.fetch_range, server.fetch_size)
    tampered = bytearray(server.content)
    tampered[location.data_offset + 10] ^= 0xFF
    server.content = bytes(tampered)

    with pytest.raises(descarga.GeodataIntegrityError, match="llegó dañado"):
        descarga.download_member(URL, location, tmp_path / "out.zip", server.fetch_range)

    assert not (tmp_path / "out.zip").exists()
    assert not (tmp_path / "out.zip.part").exists()


def test_cabecera_local_invalida(tmp_path: Path) -> None:
    server = FakeServer(make_outer_zip(make_inner_zip()))
    location = descarga.locate_member(URL, INNER_NAME, server.fetch_range, server.fetch_size)
    header_offset = location.data_offset - 30 - len(INNER_NAME)
    tampered = bytearray(server.content)
    tampered[header_offset : header_offset + 4] = b"XXXX"
    server.content = bytes(tampered)

    with pytest.raises(descarga.GeodataDownloadError, match="Cabecera inválida"):
        descarga.locate_member(URL, INNER_NAME, server.fetch_range, server.fetch_size)


def test_compresion_no_soportada(tmp_path: Path) -> None:
    location = descarga.MemberLocation("x.zip", 0, 10, 10, 0, zipfile.ZIP_BZIP2)

    with pytest.raises(descarga.GeodataDownloadError, match="no soportado"):
        descarga.download_member(URL, location, tmp_path / "x.zip", FakeServer(b"").fetch_range)


# --- Manifiesto ---------------------------------------------------------------


def make_entry(path: str, sha: str) -> descarga.ManifestEntry:
    return descarga.ManifestEntry(
        key="k",
        title="Prueba",
        url=URL,
        member=None,
        edition="2026",
        license="Dominio público",
        path=path,
        size=3,
        sha256=sha,
        downloaded_at="2026-10-15T00:00:00+00:00",
    )


def test_manifiesto_ida_y_vuelta_conserva_acentos(tmp_path: Path) -> None:
    entry = make_entry("a.zip", "abc")
    manifest_path = tmp_path / "MANIFIESTO.json"

    descarga.save_manifest(manifest_path, {"k": entry})

    assert descarga.load_manifest(manifest_path) == {"k": entry}
    assert "Dominio público" in manifest_path.read_text(encoding="utf-8")


def test_manifiesto_inexistente_es_vacio(tmp_path: Path) -> None:
    assert descarga.load_manifest(tmp_path / "no.json") == {}


def test_esta_al_dia_solo_si_el_archivo_no_cambio(tmp_path: Path) -> None:
    (tmp_path / "a.zip").write_bytes(b"abc")
    entry = make_entry("a.zip", descarga.sha256_file(tmp_path / "a.zip"))

    assert descarga.is_up_to_date(entry, tmp_path)
    (tmp_path / "a.zip").write_bytes(b"otro contenido")
    assert not descarga.is_up_to_date(entry, tmp_path)
    assert not descarga.is_up_to_date(None, tmp_path)
    assert not descarga.is_up_to_date(make_entry("falta.zip", "x"), tmp_path)


# --- Comando descargar ----------------------------------------------------------


def test_comando_descarga_registra_y_no_repite(tmp_path: Path) -> None:
    inner = make_inner_zip()
    server = FakeServer(make_outer_zip(inner))
    whole_calls: list[str] = []

    def fetch_whole(url: str) -> bytes:
        whole_calls.append(url)
        return b"paises"

    sources = [
        Source("inegi", "INEGI", URL, INNER_NAME, "2026", "inegi/mg.zip", "libre"),
        Source("ne", "NE", "https://ne.test/p.zip", None, "2022", "ne/p.zip", "dominio público"),
    ]
    manifest_path = tmp_path / "MANIFIESTO.json"
    fetchers = descarga.Fetchers(server.fetch_range, server.fetch_size, fetch_whole)

    first = descargar.run(sources, tmp_path, manifest_path, force=False, fetchers=fetchers)
    served_after_first = server.bytes_served
    second = descargar.run(sources, tmp_path, manifest_path, force=False, fetchers=fetchers)

    assert (tmp_path / "inegi/mg.zip").read_bytes() == inner
    assert first["inegi"].member == INNER_NAME
    assert first["ne"].size == len(b"paises")
    assert json.loads(manifest_path.read_text(encoding="utf-8"))["descargas"][0]["key"] == "inegi"
    # Segunda corrida: nada se vuelve a bajar.
    assert server.bytes_served == served_after_first
    assert whole_calls == ["https://ne.test/p.zip"]
    assert second == first

    descargar.run(sources, tmp_path, manifest_path, force=True, fetchers=fetchers)
    assert whole_calls == ["https://ne.test/p.zip", "https://ne.test/p.zip"]


# --- Reintentos de red ------------------------------------------------------------


class FakeResponse:
    def __init__(self, status: int, body: bytes, headers: dict[str, str] | None = None) -> None:
        self.status = status
        self._body = body
        self.headers = Message()
        for key, value in (headers or {}).items():
            self.headers[key] = value

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None


@pytest.fixture
def no_sleep(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    waits: list[float] = []
    monkeypatch.setattr(descarga.time, "sleep", waits.append)
    return waits


def test_reintenta_fallas_pasajeras_con_espera_exponencial(
    monkeypatch: pytest.MonkeyPatch, no_sleep: list[float]
) -> None:
    responses: list[Exception | FakeResponse] = [
        urllib.error.URLError("sin red"),
        urllib.error.HTTPError(URL, 503, "ocupado", Message(), None),
        FakeResponse(206, b"abcd"),
    ]

    def urlopen(*args: object, **kwargs: object) -> FakeResponse:
        item = responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    monkeypatch.setattr(descarga.urllib.request, "urlopen", urlopen)

    assert descarga.http_fetch_range(URL, 0, 3) == b"abcd"
    assert no_sleep == [2, 4]


def test_no_reintenta_errores_definitivos(
    monkeypatch: pytest.MonkeyPatch, no_sleep: list[float]
) -> None:
    def urlopen(*args: object, **kwargs: object) -> FakeResponse:
        raise urllib.error.HTTPError(URL, 404, "no existe", Message(), None)

    monkeypatch.setattr(descarga.urllib.request, "urlopen", urlopen)

    with pytest.raises(descarga.GeodataDownloadError, match="HTTP 404"):
        descarga.http_fetch_range(URL, 0, 3)
    assert no_sleep == []


def test_se_rinde_despues_del_maximo_de_intentos(
    monkeypatch: pytest.MonkeyPatch, no_sleep: list[float]
) -> None:
    def urlopen(*args: object, **kwargs: object) -> FakeResponse:
        raise urllib.error.URLError("sin red")

    monkeypatch.setattr(descarga.urllib.request, "urlopen", urlopen)

    with pytest.raises(descarga.GeodataDownloadError, match="sin red"):
        descarga.http_fetch_whole(URL)
    assert len(no_sleep) == descarga.MAX_ATTEMPTS - 1


def test_rango_incompleto_se_reintenta(
    monkeypatch: pytest.MonkeyPatch, no_sleep: list[float]
) -> None:
    responses = [FakeResponse(206, b"ab"), FakeResponse(206, b"abcd")]
    monkeypatch.setattr(descarga.urllib.request, "urlopen", lambda *a, **k: responses.pop(0))

    assert descarga.http_fetch_range(URL, 0, 3) == b"abcd"
    assert no_sleep == [2]


def test_servidor_que_ignora_range_es_error(
    monkeypatch: pytest.MonkeyPatch, no_sleep: list[float]
) -> None:
    monkeypatch.setattr(
        descarga.urllib.request, "urlopen", lambda *a, **k: FakeResponse(200, b"todo")
    )

    with pytest.raises(descarga.GeodataDownloadError, match="por partes"):
        descarga.http_fetch_range(URL, 0, 3)


def test_tamano_desde_content_length(
    monkeypatch: pytest.MonkeyPatch, no_sleep: list[float]
) -> None:
    monkeypatch.setattr(
        descarga.urllib.request,
        "urlopen",
        lambda *a, **k: FakeResponse(200, b"", {"Content-Length": "2946855741"}),
    )

    assert descarga.http_content_length(URL) == 2_946_855_741


def test_sin_content_length_es_error(
    monkeypatch: pytest.MonkeyPatch, no_sleep: list[float]
) -> None:
    monkeypatch.setattr(descarga.urllib.request, "urlopen", lambda *a, **k: FakeResponse(200, b""))

    with pytest.raises(descarga.GeodataDownloadError, match="Content-Length"):
        descarga.http_content_length(URL)
