"""Reparar texto con Mojibake: UTF-8 que alguien leyó como Windows-1252.

El Mojibake es texto con «letras raras»: ``seÃ±alÃ³`` en lugar de
``señaló``, o ``ChihuahuaðŸŽ¦`` en lugar de ``Chihuahua🎦``. Pasa cuando
un medio publica en UTF-8 pero declara otro encoding y alguien en el camino
(GDELT, en las notas medidas el 24/10/2026) lo lee como Windows-1252: cada
letra acentuada se vuelve dos o más letras. Se arregla haciendo el camino
al revés: volver a los bytes con Windows-1252 y leerlos como UTF-8.

La reparación es conservadora: solo toca secuencias que forman un carácter
UTF-8 válido **y** creíble en una nota en español (letras latinas, comillas
y guiones tipográficos, símbolos y emojis). El texto correcto
(``Peñón``, ``está``) no cambia, y un texto mitad correcto y mitad roto se
arregla solo en la parte rota.

La usan ``RawArticle.create`` y ``NewsItem.create`` para que ninguna nota
entre rota, y ``make reparar-texto`` para las que ya se guardaron.

No hace: no adivina encodings distintos de Windows-1252/Latin-1, ni quita
emojis ni corrige errores de escritura.
"""

from collections.abc import Sequence
from itertools import product

# Bytes 0x80–0x9F de Windows-1252 que sí tienen carácter (€, ‚, ƒ, „, …, ™,
# œ, Ÿ…). Los cinco que no tienen (0x81, 0x8D, 0x8F, 0x90, 0x9D) los dejan
# los decodificadores tolerantes como el carácter de control del mismo
# número, que se resuelve con la regla de Latin-1 de ``_byte_of``.
_CP1252_HIGH_START = 0x80
_CP1252_HIGH_END = 0x9F
_CP1252_BYTES: dict[str, int] = {}
for _value in range(_CP1252_HIGH_START, _CP1252_HIGH_END + 1):
    try:
        _CP1252_BYTES[bytes([_value]).decode("cp1252")] = _value
    except UnicodeDecodeError:
        continue

_ASCII_LIMIT = 0x80
_LATIN1_LIMIT = 0x100
# Rangos del primer byte de UTF-8 y cuántos bytes de continuación le siguen
# (RFC 3629 §4). C0, C1 y F5–FF nunca abren un carácter válido.
_LEAD_2 = (0xC2, 0xDF)
_LEAD_3 = (0xE0, 0xEF)
_LEAD_4 = (0xF0, 0xF4)
_CONTINUATION = (0x80, 0xBF)
# Caracteres que se aceptan como resultado: los que de verdad aparecen en
# notas en español. Cualquier otro (cirílico, CJK…) indica que la secuencia
# no era Mojibake sino texto legítimo, por ejemplo «ADIÓS”».
_PLAUSIBLE_RANGES = (
    (0x00A0, 0x017F),  # Latin-1 y Latin Extended-A: á, ñ, ¿, º, œ…
    (0x2010, 0x206F),  # Puntuación tipográfica: – — ‘ ’ “ ” … •
    (0x20AC, 0x20AC),  # €
    (0x2100, 0x2BFF),  # Símbolos, flechas, ™, ★, ✅
    (0xFE00, 0xFE0F),  # Selectores de variante que acompañan a los emojis
    (0x1F000, 0x1FAFF),  # Emojis y pictogramas: 🎦 📹 🚨
)
# Caracteres de control C1 (U+0080–U+009F): nunca son texto real.
_C1_START = 0x80
_C1_END = 0x9F
# GDELT cambia las comillas tipográficas por comillas rectas, y con eso
# borra el byte que formaba la letra: «Órdenes» (C3 93) llega como
# ``Ã"rdenes`` y 📸 (F0 9F 93 B8) como ``ðŸ"¸`` (medido el 24/10/2026 en
# hoytamaulipas.net). Una comilla recta en medio de una secuencia rota se
# prueba como 0x93 («“») y luego como 0x94 («”»).
_ASCII_QUOTE = '"'
_QUOTE_BYTES = (0x93, 0x94)
# Una nota doblemente rota (Mojibake de Mojibake) necesita dos pasadas; tres
# es el tope para no ciclar nunca.
MAX_PASSES = 3


def _byte_of(char: str) -> int | None:
    """Byte que habría producido ``char`` al leer UTF-8 como Windows-1252."""
    code = ord(char)
    if code < _ASCII_LIMIT:
        return code
    cp1252 = _CP1252_BYTES.get(char)
    if cp1252 is not None:
        return cp1252
    return code if code < _LATIN1_LIMIT else None


def _continuations(lead: int) -> int:
    """Cuántos bytes de continuación espera un primer byte de UTF-8."""
    for (low, high), count in ((_LEAD_2, 1), (_LEAD_3, 2), (_LEAD_4, 3)):
        if low <= lead <= high:
            return count
    return 0


def _plausible(char: str) -> bool:
    code = ord(char)
    return any(low <= code <= high for low, high in _PLAUSIBLE_RANGES)


def _continuation_candidates(char: str) -> tuple[int, ...]:
    """Bytes de continuación que pudo ser ``char`` (vacío si ninguno)."""
    if char == _ASCII_QUOTE:
        return _QUOTE_BYTES
    byte = _byte_of(char)
    if byte is None or not _CONTINUATION[0] <= byte <= _CONTINUATION[1]:
        return ()
    return (byte,)


def _decode(chunk: Sequence[int]) -> str | None:
    """El carácter que forman los bytes, si es uno solo y creíble."""
    try:
        decoded = bytes(chunk).decode("utf-8")
    except UnicodeDecodeError:
        return None
    if len(decoded) != 1:
        return None
    if _C1_START <= ord(decoded) <= _C1_END:
        # Doble error: el medio escribió en Windows-1252 («…» = 0x85), alguien
        # lo leyó como Latin-1 (control U+0085) y luego se rompió como UTF-8.
        decoded = bytes([ord(decoded)]).decode("cp1252", errors="replace")
    return decoded if _plausible(decoded) else None


def _repair_once(text: str) -> str:
    out: list[str] = []
    i = 0
    while i < len(text):
        lead = _byte_of(text[i])
        count = _continuations(lead) if lead is not None else 0
        # ``i + count < len(text)``: deben caber todos los bytes de continuación.
        if lead is not None and count and i + count < len(text):
            options = [_continuation_candidates(c) for c in text[i + 1 : i + 1 + count]]
            # Las opciones van en orden de preferencia; gana la primera que
            # forme un carácter creíble.
            decoded = next(
                (d for tail in product(*options) if (d := _decode((lead, *tail)))),
                None,
            )
            if decoded:
                out.append(decoded)
                i += count + 1
                continue
        out.append(text[i])
        i += 1
    return "".join(out)


def repair_mojibake(text: str) -> str:
    """Repara las partes de ``text`` que son UTF-8 leído como Windows-1252.

    Args:
        text: Título, fragmento o nombre de medio.

    Returns:
        El texto reparado. Si no tenía Mojibake, el mismo texto.

    Example:
        >>> repair_mojibake("Maru seÃ±alÃ³ corrupciÃ³n de su exfiscal")
        'Maru señaló corrupción de su exfiscal'
        >>> repair_mojibake("Peñón de los Baños")
        'Peñón de los Baños'
    """
    for _ in range(MAX_PASSES):
        repaired = _repair_once(text)
        if repaired == text:
            break
        text = repaired
    return text


def clean_text(text: str | None) -> str | None:
    """Limpia un texto de una fuente: repara el Mojibake y junta espacios.

    Args:
        text: Texto tal como llegó, o ``None``.

    Returns:
        El texto limpio, o ``None`` si quedó vacío.
    """
    if text is None:
        return None
    cleaned = " ".join(repair_mojibake(text).split())
    return cleaned or None
