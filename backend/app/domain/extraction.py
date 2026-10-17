"""Qué texto se procesa de cada nota (especificación §9, paso 4; ADR-0015).

Se intenta leer el cuerpo de la nota en la página del medio. Si no se puede
(muro de pago, bloqueo, página rara) o lo que sale es demasiado corto para
ser un artículo, se usa **título + fragmento** y la nota queda marcada como
``fallback``: no se pierde, solo se procesa con menos información.

El texto sirve para la IA y nunca se muestra (CLAUDE.md §8).

No hace: no baja páginas (eso es el adaptador de extracción).
"""

import hashlib
from dataclasses import dataclass
from enum import StrEnum

from app.domain.names import normalize_name

# Menos que esto no es el cuerpo de una nota: suelen ser avisos de cookies,
# "suscríbete para leer" o un pie de foto. Decisión de F4, a revisar con las
# 5 extracciones reales.
MIN_ARTICLE_CHARS = 300
# Palabras del título que cuentan para comprobar que el cuerpo es de esta
# nota: las de 5 letras o más (evita "de", "los", "para"...). Con 2 en común
# basta; títulos con menos palabras largas piden todas.
TITLE_WORD_MIN_CHARS = 5
TITLE_WORDS_REQUIRED = 2


class ExtractionStatus(StrEnum):
    """Columna ``articles.extraction_status``."""

    OK = "ok"
    FALLBACK = "fallback"


@dataclass(frozen=True, slots=True)
class ProcessingText:
    """El texto que se procesará de una nota.

    Attributes:
        text: Cuerpo extraído, o título + fragmento.
        status: ``ok`` si es el cuerpo; ``fallback`` si no.
        reason: Por qué se usó el respaldo, si se usó.
    """

    text: str
    status: ExtractionStatus
    reason: str | None = None

    @property
    def text_hash(self) -> str:
        """Huella del texto: llave de la caché de la IA (§10)."""
        return hashlib.sha256(self.text.encode("utf-8")).hexdigest()


def mentions_title(body: str, title: str) -> bool:
    """Dice si el cuerpo habla de la nota del título y no de otra.

    Hay páginas con varias notas (medido el 16/10/2026: una URL del RSS de La
    Jornada trajo el cuerpo de otra nota de la misma sección). Si ninguna de
    las palabras largas del título aparece en el cuerpo, el texto no es de
    esta nota.

    Args:
        body: Cuerpo extraído.
        title: Título de la nota.

    Returns:
        ``True`` si al menos una palabra significativa del título está en el
        cuerpo, o si el título no tiene palabras significativas.
    """
    words = {w for w in normalize_name(title).split() if len(w) >= TITLE_WORD_MIN_CHARS}
    if not words:
        return True
    body_words = set(normalize_name(body).split())
    return len(words & body_words) >= min(TITLE_WORDS_REQUIRED, len(words))


def processing_text(
    title: str, snippet: str | None, extracted: str | None, failure: str | None = None
) -> ProcessingText:
    """Decide qué texto se procesa.

    Args:
        title: Título de la nota.
        snippet: Fragmento del proveedor, si lo hay.
        extracted: Cuerpo extraído, si se pudo.
        failure: Motivo si la extracción falló.

    Returns:
        El cuerpo si es suficiente; si no, título + fragmento con su motivo.

    Example:
        >>> processing_text("Hackeo", "Atacan la alcaldía", None, "HTTP 403").status
        <ExtractionStatus.FALLBACK: 'fallback'>
    """
    body = " ".join((extracted or "").split())
    if len(body) >= MIN_ARTICLE_CHARS and mentions_title(body, title):
        return ProcessingText(body, ExtractionStatus.OK)
    if failure:
        reason = failure
    elif not body:
        reason = "La página no trajo texto."
    elif len(body) < MIN_ARTICLE_CHARS:
        reason = f"Texto muy corto ({len(body)} caracteres)."
    else:
        reason = "El texto de la página es de otra nota (no menciona el título)."
    fallback = " ".join(f"{title}. {snippet or ''}".split())
    return ProcessingText(fallback, ExtractionStatus.FALLBACK, reason)
