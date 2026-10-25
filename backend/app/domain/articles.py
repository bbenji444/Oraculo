"""Nota tal como la entrega un proveedor, ya en el formato común (``RawArticle``).

Cada proveedor responde distinto (JSON de SearchApi, JSON de GDELT, XML del
RSS de Google). Los adaptadores traducen cada respuesta a ``RawArticle``
para que el resto del sistema no dependa de ningún formato (especificación
§8). Reglas que garantiza este módulo:

- La URL es absoluta, ``http`` o ``https``.
- El título no está vacío; los espacios se limpian y el Mojibake se repara
  (text_repair, F12.1).
- Las fechas van en UTC. Si el proveedor no da fecha, queda ``None``: nunca
  se inventa.

No hace: no deduplica ni lee el texto de la nota (eso es F4).
"""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import urlsplit

from app.domain.queries import Provider
from app.domain.text_repair import clean_text

_WEB_SCHEMES = frozenset({"http", "https"})
_WWW = "www."


class InvalidArticleError(ValueError):
    """Un resultado del proveedor no se puede usar (sin URL válida o sin título).

    El adaptador lo descarta y sigue con los demás: un resultado roto no
    debe tumbar la consulta.
    """


def domain_of(url: str) -> str | None:
    """Dominio de una URL, sin ``www.`` y en minúsculas.

    Args:
        url: URL absoluta.

    Returns:
        ``"eluniversal.com.mx"``, o ``None`` si la URL no tiene dominio.

    Example:
        >>> domain_of("https://www.ElUniversal.com.mx/metropoli/nota")
        'eluniversal.com.mx'
    """
    host = (urlsplit(url).hostname or "").lower()
    if host.startswith(_WWW):
        host = host[len(_WWW) :]
    return host or None


@dataclass(frozen=True, slots=True)
class RawArticle:
    """Una nota encontrada por un proveedor, en el formato común (§8).

    Se construye con ``RawArticle.create`` para que nunca exista una nota
    que no cumpla las reglas.

    Attributes:
        provider: Proveedor que la encontró.
        provider_rank: Posición en sus resultados (1 = primera).
        url: Link a la nota (en Google News RSS, el link de Google).
        title: Título limpio.
        source_name: Nombre del medio ("El Universal"), si viene.
        source_domain: Dominio del medio ("eluniversal.com.mx"), si se conoce.
        published_at: Fecha de publicación en UTC, si el proveedor la da.
        snippet: Fragmento o resumen del proveedor, si viene.
        language: Idioma que reporta el proveedor, si lo reporta.
        raw: El resultado original del proveedor, para depurar.
    """

    provider: Provider
    provider_rank: int
    url: str
    title: str
    source_name: str | None
    source_domain: str | None
    published_at: datetime | None
    snippet: str | None
    language: str | None
    raw: Mapping[str, object]

    @classmethod
    def create(  # noqa: PLR0913 — un argumento por campo del contrato §8, todos por nombre (*)
        cls,
        *,
        provider: Provider,
        provider_rank: int,
        url: str,
        title: str | None,
        source_name: str | None = None,
        source_domain: str | None = None,
        published_at: datetime | None = None,
        snippet: str | None = None,
        language: str | None = None,
        raw: Mapping[str, object] | None = None,
    ) -> "RawArticle":
        """Valida y limpia un resultado.

        Args:
            provider: Proveedor.
            provider_rank: Posición (desde 1).
            url: Link absoluto ``http(s)``.
            title: Título; no puede quedar vacío.
            source_name: Nombre del medio.
            source_domain: Dominio del medio; si falta, se toma de ``url``.
            published_at: Fecha con zona horaria; se convierte a UTC.
            snippet: Fragmento.
            language: Idioma.
            raw: Resultado original.

        Returns:
            La nota en el formato común.

        Raises:
            InvalidArticleError: Si la URL no es web, falta el título, la
                posición es menor que 1 o la fecha no trae zona horaria.
        """
        clean_url = url.strip()
        parts = urlsplit(clean_url)
        if parts.scheme not in _WEB_SCHEMES or not parts.netloc:
            raise InvalidArticleError(f"URL no válida: {url!r}")
        clean_title = clean_text(title)
        if clean_title is None:
            raise InvalidArticleError(f"Resultado sin título: {url!r}")
        if provider_rank < 1:
            raise InvalidArticleError(f"Posición no válida: {provider_rank}")
        if published_at is not None and published_at.tzinfo is None:
            # Una fecha sin zona es ambigua: ¿hora de México o UTC? Mejor
            # que el adaptador la resuelva explícitamente.
            raise InvalidArticleError(f"Fecha sin zona horaria: {published_at.isoformat()}")
        return cls(
            provider=provider,
            provider_rank=provider_rank,
            url=clean_url,
            title=clean_title,
            source_name=clean_text(source_name),
            source_domain=(source_domain or domain_of(clean_url) or "").lower() or None,
            published_at=published_at.astimezone(UTC) if published_at else None,
            snippet=clean_text(snippet),
            language=clean_text(language),
            raw=dict(raw or {}),
        )
