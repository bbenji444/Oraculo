"""Casos de uso de la ingesta con fuentes, índice y registro falsos."""

from datetime import timedelta

import pytest

from app.application.ports.ingest import GkgFile, IngestSourceError, MediaFeed, ParseResult
from app.application.use_cases.ingest import (
    SAMPLE_SIZE,
    IngestGdeltGkg,
    IngestMediaRss,
    PlanGdeltHistory,
    PurgeNewsIndex,
)
from app.domain.errors import ProviderUnavailableError
from tests.unit.fake_ingest import FILE, NOW, FakeGkg, FakeIndex, FakeRuns, parsed

pytestmark = pytest.mark.anyio


async def test_gdelt_guarda_las_notas_y_registra_la_corrida() -> None:
    index, runs = FakeIndex(), FakeRuns()

    report = await IngestGdeltGkg(FakeGkg(parsed(8)), index, runs, clock=lambda: NOW).run()

    assert (report.status, report.items_new, report.items_kept, report.items_seen) == (
        "ok",
        8,
        8,
        24,
    )
    assert len(report.sample) == SAMPLE_SIZE
    assert report.item == FILE.name
    [run] = runs.runs
    assert (run.status, run.dedupe_key, run.bytes_downloaded) == ("ok", FILE.url, 8_000_000)


async def test_un_archivo_ya_procesado_no_se_vuelve_a_bajar() -> None:
    source, runs = FakeGkg(parsed(3)), FakeRuns(processed=[FILE.url])

    report = await IngestGdeltGkg(source, FakeIndex(), runs).run()

    assert report.status == "skipped"
    assert source.fetched == 0
    assert runs.runs == []


async def test_dos_corridas_seguidas_procesan_el_archivo_una_vez() -> None:
    source, index, runs = FakeGkg(parsed(3)), FakeIndex(), FakeRuns()
    use_case = IngestGdeltGkg(source, index, runs)

    first, second = await use_case.run(), await use_case.run()

    assert (first.status, second.status) == ("ok", "skipped")
    assert source.fetched == 1


@pytest.mark.parametrize(
    "failure",
    [
        IngestSourceError("El archivo llegó incompleto"),
        ProviderUnavailableError("GDELT no responde", provider="gdelt"),
    ],
)
async def test_un_archivo_que_falla_queda_registrado_como_error(failure: Exception) -> None:
    runs = FakeRuns()

    report = await IngestGdeltGkg(FakeGkg(failure), FakeIndex(), runs).run()

    assert report.status == "error"
    assert runs.runs[0].status == "error"
    assert runs.runs[0].dedupe_key == FILE.url
    # Un error no marca el archivo como procesado: la siguiente corrida reintenta.
    assert FILE.url not in runs.processed


async def test_si_falla_el_anuncio_se_registra_sin_archivo() -> None:
    runs = FakeRuns()
    source = FakeGkg(parsed(1), latest=IngestSourceError("no anuncia un GKG"))

    report = await IngestGdeltGkg(source, FakeIndex(), runs).run()

    assert report.status == "error"
    assert runs.runs[0].dedupe_key is None
    assert "no anuncia" in (runs.runs[0].error_message or "")


class FakeFeeds:
    def __init__(self, failing: set[str]) -> None:
        self.failing = failing
        self.read: list[str] = []

    async def fetch(self, feed: MediaFeed) -> tuple[ParseResult, int]:
        self.read.append(feed.slug)
        if feed.slug in self.failing:
            raise IngestSourceError("No es un RSS")
        return parsed(2, feed.source), 1000


FEEDS = [
    MediaFeed("la-jornada", "La Jornada", "https://jornada.example/rss", active=True),
    MediaFeed("roto", "Roto", "https://roto.example/rss", active=True),
    MediaFeed("inactivo", "Inactivo", "https://inactivo.example/rss", active=False),
]


async def test_rss_lee_solo_activos_y_un_medio_roto_no_detiene_a_los_demas() -> None:
    source, runs = FakeFeeds(failing={"roto"}), FakeRuns()

    reports = await IngestMediaRss(source, FEEDS, FakeIndex(), runs).run()

    assert source.read == ["la-jornada", "roto"]
    assert [(r.source, r.status) for r in reports] == [
        ("rss:la-jornada", "ok"),
        ("rss:roto", "error"),
    ]
    assert all(run.dedupe_key is None for run in runs.runs)


async def test_sin_medios_activos_no_hace_nada() -> None:
    source = FakeFeeds(failing=set())

    reports = await IngestMediaRss(source, FEEDS[2:], FakeIndex(), FakeRuns()).run()

    assert (reports, source.read) == ([], [])


async def test_la_limpieza_borra_lo_anterior_a_la_retencion() -> None:
    index = FakeIndex()

    deleted = await PurgeNewsIndex(index, retention_days=90, clock=lambda: NOW).run()

    assert deleted == 7
    assert index.cutoff == NOW - timedelta(days=90)


# --- Historial (vista previa sin bajar) ---


def gkg(stamp: str, size: int) -> GkgFile:
    return GkgFile(
        f"https://data.gdeltproject.org/gdeltv2/{stamp}.translation.gkg.csv.zip", size, "m"
    )


async def test_el_plan_mide_sin_bajar_y_salta_lo_ya_procesado() -> None:
    nuevo, viejo = gkg("20261016200000", 7_000_000), gkg("20261016194500", 6_000_000)
    hecho = "https://data.gdeltproject.org/gdeltv2/20261016193000.translation.gkg.csv.zip"
    hueco = "https://data.gdeltproject.org/gdeltv2/20261016191500.translation.gkg.csv.zip"
    roto = "https://data.gdeltproject.org/gdeltv2/20261016190000.translation.gkg.csv.zip"
    source = FakeGkg(
        parsed(1),
        history={
            nuevo.url: nuevo,
            viejo.url: viejo,
            hueco: None,
            roto: IngestSourceError("sin MD5"),
        },
    )
    progress: list[tuple[int, int]] = []

    plan = await PlanGdeltHistory(source, FakeRuns(processed=[hecho])).plan(
        [nuevo.url, viejo.url, hecho, hueco, roto], lambda d, t: progress.append((d, t))
    )

    assert plan.files == (nuevo, viejo)
    assert (plan.already_done, plan.missing, plan.total_bytes) == (1, 1, 13_000_000)
    assert plan.failed == (f"{roto}: sin MD5",)
    # Lo ya procesado ni siquiera se mide, y nada se baja.
    assert hecho not in source.described
    assert source.fetched == 0
    assert progress[-1] == (5, 5)


async def test_un_archivo_del_historial_pasa_por_el_mismo_camino() -> None:
    file, runs = gkg("20261009120000", 13_000_000), FakeRuns()
    use_case = IngestGdeltGkg(FakeGkg(parsed(3)), FakeIndex(), runs)

    first, second = await use_case.run_file(file), await use_case.run_file(file)

    assert (first.status, first.items_new, second.status) == ("ok", 3, "skipped")
    assert runs.runs[0].dedupe_key == file.url


async def test_el_plan_funciona_sin_aviso_de_avance() -> None:
    file = gkg("20261016200000", 1)

    plan = await PlanGdeltHistory(FakeGkg(parsed(1), history={file.url: file}), FakeRuns()).plan(
        [file.url]
    )

    assert plan.files == (file,)
