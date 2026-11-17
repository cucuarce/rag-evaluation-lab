"""Regla explícita para distinguir consultas sobre lo vigente de consultas históricas.

Solo mira el TEXTO de la pregunta (nunca etiquetas). Es una regla léxica, determinística y
deliberadamente simple; sus errores posibles están documentados en docs/generation.md.

Resultado (`TemporalScope.kind`):
- "historical_anchored": la pregunta menciona un momento pasado identificable
  ("antes de marzo de 2026", "en 2025", "la versión 2", "la política anterior"...).
  -> usar la versión cuya vigencia cubre ese momento, aunque esté deprecated.
- "historical_unanchored": hay marcas de pasado ("era", "regía", "solía", "anteriormente")
  pero ningún momento identificable. -> si las versiones disponibles discrepan, no adivinar:
  abstenerse y pedir la fecha o período.
- "current": todo lo demás (por defecto). -> usar solo documentos vigentes.

Un año explícito solo cuenta como histórico si es anterior al año de `reference_date`, y una
fecha "antes de <fecha>" solo si esa fecha no es posterior a `reference_date`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

from rag_lab.text import strip_accents

MONTHS = {
    "enero": 1,
    "febrero": 2,
    "marzo": 3,
    "abril": 4,
    "mayo": 5,
    "junio": 6,
    "julio": 7,
    "agosto": 8,
    "septiembre": 9,
    "setiembre": 9,
    "octubre": 10,
    "noviembre": 11,
    "diciembre": 12,
}
_MONTH = "|".join(MONTHS)

# "antes de/del [1 de] [marzo de] 2026"
_BEFORE_DATE = re.compile(
    rf"\bantes del?\s+(?:(?P<day>\d{{1,2}})\s+de\s+)?(?:(?P<month>{_MONTH})\s+(?:de\s+|del\s+)?)?"
    r"(?P<year>(?:19|20)\d{2})\b"
)
# "en/durante/hasta [el año] [marzo de] 2025"
_IN_YEAR = re.compile(
    rf"\b(?:en|durante|hasta|desde)\s+(?:el\s+)?(?:ano\s+)?(?:(?:{_MONTH})\s+(?:de\s+)?)?"
    r"(?P<year>(?:19|20)\d{2})\b"
)
_PRIOR_VERSION = re.compile(
    r"\b(?:version|politica|condiciones|regla|reglas)\s+"
    r"(?:anterior|previa|vieja|antigua|historica|\d+)\b"
    r"|\bv\d+\b|\bantes del? (?:cambio|la actualizacion)\b"
)
_PAST_MARKERS = re.compile(
    r"\b(?:era|eran|regia|regian|solia|solian|anteriormente|antiguamente|"
    r"estaba vigente|estuvo vigente|estaban vigentes|historico|historica)\b"
)


@dataclass(frozen=True)
class TemporalScope:
    kind: str  # "current" | "historical_anchored" | "historical_unanchored"
    evidence: str | None  # fragmento de la pregunta que disparó la regla


def classify_temporal_scope(question: str, reference_date: str) -> TemporalScope:
    ref = date.fromisoformat(reference_date)
    text = strip_accents(question).lower()

    for m in _BEFORE_DATE.finditer(text):
        year = int(m["year"])
        month = MONTHS[m["month"]] if m["month"] else 1
        day = int(m["day"]) if m["day"] else 1
        try:
            when = date(year, month, day)
        except ValueError:
            continue
        if when <= ref:
            return TemporalScope("historical_anchored", m.group(0))
    for m in _IN_YEAR.finditer(text):
        if int(m["year"]) < ref.year:
            return TemporalScope("historical_anchored", m.group(0))
    m = _PRIOR_VERSION.search(text)
    if m:
        return TemporalScope("historical_anchored", m.group(0))
    m = _PAST_MARKERS.search(text)
    if m:
        return TemporalScope("historical_unanchored", m.group(0))
    return TemporalScope("current", None)
