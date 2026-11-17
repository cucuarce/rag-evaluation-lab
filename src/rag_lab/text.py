"""Tokenización léxica para BM25 (español, sin stemming).

1. Normalización Unicode NFKD y eliminación de diacríticos (á→a, ñ→n).
2. Minúsculas.
3. Tokens: números con separadores internos ('5.000', '99,9') o secuencias alfanuméricas.
4. Se eliminan stopwords de una lista fija (abajo). No se aplica stemming: 'factura' y
   'facturas' son tokens distintos. Es una limitación conocida y documentada.
"""

from __future__ import annotations

import re
import unicodedata

_TOKEN = re.compile(r"\d+(?:[.,]\d+)*|[a-z0-9]+")

STOPWORDS = frozenset(
    """
    a al algo algun alguna algunas alguno algunos ante antes como con contra cual cuales
    cuando de del desde donde durante e el ella ellas ellos en entre era es esa esas ese eso
    esos esta estas este esto estos fue fueron ha han hasta hay la las le les lo los mas me
    mi mis muy ni no o os otra otras otro otros para pero poco por porque que quien se
    ser si sin sobre son su sus tambien te tiene tienen todo todos tu tus un una unas uno
    unos y ya puede pueden debe cada
    """.split()
)


def strip_accents(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))


def tokenize(text: str) -> list[str]:
    norm = strip_accents(text).lower()
    return [t for t in _TOKEN.findall(norm) if t not in STOPWORDS]
