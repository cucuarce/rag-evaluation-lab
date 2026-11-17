"""Validación de la respuesta estructurada del modelo.

Nunca se "arregla" una respuesta: si el JSON es inválido o no respeta el esquema se registra
`format_error`; las citas a fragmentos no suministrados se descartan del conjunto válido y se
registran como `invalid_citations` (el conteo entra en las métricas).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from rag_lab.generation.prompt import ABSTAIN_REASONS


@dataclass(frozen=True)
class ParsedAnswer:
    format_ok: bool
    format_error: str | None
    answer: str | None = None
    abstain: bool | None = None
    abstain_reason: str | None = None
    citations_raw: tuple[str, ...] = ()
    valid_citations: tuple[str, ...] = ()  # cite_ids suministrados, sin duplicados, en orden
    invalid_citations: tuple[str, ...] = ()
    consistency_issues: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict:
        return {
            "format_ok": self.format_ok,
            "format_error": self.format_error,
            "answer": self.answer,
            "abstain": self.abstain,
            "abstain_reason": self.abstain_reason,
            "citations_raw": list(self.citations_raw),
            "valid_citations": list(self.valid_citations),
            "invalid_citations": list(self.invalid_citations),
            "consistency_issues": list(self.consistency_issues),
        }


def parse_answer(raw: str | None, allowed_cite_ids: list[str]) -> ParsedAnswer:
    if raw is None or not raw.strip():
        return ParsedAnswer(False, "empty_response")
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError as exc:
        return ParsedAnswer(False, f"invalid_json: {exc.msg}")
    if not isinstance(obj, dict):
        return ParsedAnswer(False, "not_an_object")
    expected = {"answer", "citations", "abstain", "abstain_reason"}
    if set(obj) != expected:
        return ParsedAnswer(False, f"keys {sorted(obj)} != {sorted(expected)}")
    answer, citations = obj["answer"], obj["citations"]
    abstain, reason = obj["abstain"], obj["abstain_reason"]
    if not isinstance(answer, str):
        return ParsedAnswer(False, "answer no es string")
    if not isinstance(abstain, bool):
        return ParsedAnswer(False, "abstain no es booleano")
    if reason not in ABSTAIN_REASONS:
        return ParsedAnswer(False, f"abstain_reason inválido: {reason!r}")
    if not isinstance(citations, list) or not all(isinstance(c, str) for c in citations):
        return ParsedAnswer(False, "citations no es lista de strings")

    allowed = set(allowed_cite_ids)
    valid: list[str] = []
    invalid: list[str] = []
    for c in citations:
        cid = c.strip().strip("[]").strip()
        if cid in allowed:
            if cid not in valid:
                valid.append(cid)
        else:
            invalid.append(c)

    issues = []
    if abstain and reason == "none":
        issues.append("abstain_true_sin_motivo")
    if not abstain and reason != "none":
        issues.append("abstain_false_con_motivo")
    if not abstain and not valid:
        issues.append("respuesta_sin_citas_validas")
    if abstain and valid:
        issues.append("abstencion_con_citas")
    if not answer.strip():
        issues.append("answer_vacio")
    return ParsedAnswer(
        format_ok=True,
        format_error=None,
        answer=answer,
        abstain=abstain,
        abstain_reason=reason,
        citations_raw=tuple(citations),
        valid_citations=tuple(valid),
        invalid_citations=tuple(invalid),
        consistency_issues=tuple(issues),
    )
