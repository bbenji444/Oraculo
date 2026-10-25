"""Fábrica de adaptadores: banderas y llaves de la configuración."""

import logging

import pytest
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import create_async_engine

from app.adapters.providers.factory import build_provider
from app.core.config import Settings
from app.domain.queries import Provider


def settings(
    *,
    news_rss_enabled: bool = False,
    gdelt_enabled: bool = False,
    searchapi_api_key: SecretStr | None = None,
) -> Settings:
    # model_construct: solo los valores que importan aquí, sin leer .env.
    return Settings.model_construct(
        news_rss_enabled=news_rss_enabled,
        gdelt_enabled=gdelt_enabled,
        searchapi_api_key=searchapi_api_key,
    )


def test_google_news_rss_esta_activado_por_defecto() -> None:
    # ADR-0021 sustituye al 0011: aprobado para producción.
    assert Settings.model_fields["news_rss_enabled"].default is True


def test_rss_activo_ya_no_advierte_y_apagado_no_consulta(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.WARNING):
        provider = build_provider(Provider.GOOGLE_NEWS_RSS, settings(news_rss_enabled=True))

    assert provider.is_configured() is True
    # Ya no es "solo desarrollo": la advertencia de cada arranque se quitó.
    assert "solo para desarrollo" not in caplog.text
    assert build_provider(Provider.GOOGLE_NEWS_RSS, settings()).is_configured() is False


@pytest.mark.parametrize("key", [None, SecretStr("")])
def test_searchapi_sin_llave_no_esta_configurado(key: SecretStr | None) -> None:
    assert (
        build_provider(Provider.SEARCHAPI, settings(searchapi_api_key=key)).is_configured() is False
    )


def test_searchapi_con_llave_y_gdelt_habilitado_estan_configurados() -> None:
    with_key = settings(searchapi_api_key=SecretStr("llave"))

    assert build_provider(Provider.SEARCHAPI, with_key).is_configured() is True
    assert build_provider(Provider.GDELT, settings(gdelt_enabled=True)).is_configured() is True


def test_gdelt_esta_desactivado_por_defecto() -> None:
    assert Settings.model_fields["gdelt_enabled"].default is False
    assert build_provider(Provider.GDELT, settings()).is_configured() is False


def test_el_indice_local_necesita_la_base() -> None:
    with pytest.raises(ValueError, match="engine"):
        build_provider(Provider.LOCAL_INDEX, settings())


def test_el_indice_local_siempre_esta_disponible_y_es_gratis() -> None:
    engine = create_async_engine("postgresql+psycopg://x@localhost/no_se_conecta")

    provider = build_provider(Provider.LOCAL_INDEX, settings(), engine)

    assert provider.provider is Provider.LOCAL_INDEX
    assert provider.is_configured() is True
