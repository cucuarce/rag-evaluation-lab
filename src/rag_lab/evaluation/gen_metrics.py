"""Métricas determinísticas de generación (Etapa 2). Ver docs/generation.md.

Ninguna de estas métricas es "faithfulness": verificar que una cita exista o que apunte a un
chunk etiquetado no prueba que la respuesta esté respaldada semánticamente por ese chunk.
Faithfulness semántica (juez + contraste humano) queda para la Etapa 3.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from statistics import mean

from rag_lab.evaluation.labels import Label
from rag_lab.evaluation.metrics import covers, score_question
from rag_lab.text import strip_accents

NUMBER_WORDS = {
    "cero": "0",
    "uno": "1",
    "una": "1",
    "dos": "2",
    "tres": "3",
    "cuatro": "4",
    "cinco": "5",
    "seis": "6",
    "siete": "7",
    "ocho": "8",
    "nueve": "9",
    "diez": "10",
    "once": "11",
    "doce": "12",
    "trece": "13",
    "catorce": "14",
    "quince": "15",
    "veinte": "20",
    "treinta": "30",
}
_NUM_WORD_RE = re.compile(r"\b(" + "|".join(NUMBER_WORDS) + r")\b")


def normalize_text(text: str) -> str:
    t = strip_accents(text).lower()
    t = _NUM_WORD_RE.sub(lambda m: NUMBER_WORDS[m.group(1)], t)
    return re.sub(r"\s+", " ", t).strip()


def fact_present(fact: str, answer: str) -> bool:
    """Coincidencia léxica normalizada con límites: '5' no matchea '15' ni '5,5'."""
    f = normalize_text(fact)
    if not f:
        return False
    pattern = rf"(?<![\w]){re.escape(f)}(?![\w]|[.,]\d)"
    return re.search(pattern, normalize_text(answer)) is not None


@dataclass(frozen=True)
class _Chunk:
    chunk_id: str
    doc_id: str
    start: int
    end: int
    status: str


def _chunks(context: list[dict]) -> dict[str, _Chunk]:
    return {
        c["chunk_id"]: _Chunk(c["chunk_id"], c["doc_id"], c["start"], c["end"], c["status"])
        for c in context
    }


def label_temporal_kind(label: Label, deprecated: set[str]) -> str:
    """'historical' si algún requisito solo puede satisfacerse con documentos deprecated."""
    for req in label.gold:
        if all(s.doc_id in deprecated for s in req.alternatives):
            return "historical"
    return "current"


def score_generation_row(gen: dict, label: Label, tau: float, deprecated: set[str]) -> dict:
    ctx = _chunks(gen.get("context", []))
    ordered = list(ctx.values())
    out: dict = {
        "qid": gen["qid"],
        "category": label.category,
        "answerable": label.answerable,
        "status": gen["status"],
        "temporal_rule": (gen.get("temporal_scope") or {}).get("kind"),
        "abstained": gen.get("abstained"),
        "abstain_cause": gen.get("abstain_cause"),
    }
    if gen["status"] != "ok":
        return out

    if label.answerable:
        rm = score_question(ordered, label, tau, deprecated)
        out["retrieval_complete"] = rm.complete
        out["label_temporal_kind"] = label_temporal_kind(label, deprecated)
        out["temporal_rule_agrees"] = (out["temporal_rule"] == "current") == (
            out["label_temporal_kind"] == "current"
        )

    exposed_deprecated = any(c.status == "deprecated" for c in ordered)
    out["context_has_deprecated"] = exposed_deprecated

    if gen["abstained"]:
        if label.answerable:
            out["over_abstention"] = int(out["retrieval_complete"] == 1)
            out["abstained_with_incomplete_evidence"] = int(out["retrieval_complete"] == 0)
        else:
            out["correct_abstention"] = 1
        return out

    # Respondió.
    llm = gen.get("llm") or {}
    parsed = llm.get("parsed") or {}
    n_raw = len(parsed.get("citations_raw", []))
    n_invalid = len(parsed.get("invalid_citations", []))
    cited = [ctx[c] for c in gen.get("cited_chunk_ids", [])]
    answer = gen.get("answer") or ""
    out.update(
        {
            "n_citations": n_raw,
            "n_invalid_citations": n_invalid,
            "citation_validity": None if n_raw == 0 else round((n_raw - n_invalid) / n_raw, 6),
            "uncited_answer": int(not cited),
            "consistency_issues": parsed.get("consistency_issues", []),
        }
    )
    if not label.answerable:
        out["improper_answer"] = 1
        if label.forbidden_facts:
            out["forbidden_present"] = int(
                any(fact_present(f, answer) for f in label.forbidden_facts)
            )
        return out

    gold_ids = {
        c.chunk_id
        for c in cited
        if any(covers(c, s, tau) for req in label.gold for s in req.alternatives)
    }
    satisfied = {
        req.id
        for req in label.gold
        if any(covers(c, s, tau) for c in cited for s in req.alternatives)
    }
    req_hits = [fact_present(f, answer) for f in label.required_facts]
    out.update(
        {
            "answered_with_incomplete_evidence": int(out["retrieval_complete"] == 0),
            "citation_precision": None if not cited else round(len(gold_ids) / len(cited), 6),
            "cited_evidence_recall": round(len(satisfied) / len(label.gold), 6),
            "required_facts_coverage": round(mean(req_hits), 6) if req_hits else None,
            "all_required_facts": int(all(req_hits)) if req_hits else None,
            "missing_facts": [
                f for f, h in zip(label.required_facts, req_hits, strict=True) if not h
            ],
        }
    )
    if label.forbidden_facts:
        found = [f for f in label.forbidden_facts if fact_present(f, answer)]
        out["forbidden_present"] = int(bool(found))
        out["forbidden_found"] = found

    # Selección de versión.
    cites_deprecated = any(c.status == "deprecated" for c in cited)
    if out["label_temporal_kind"] == "historical":
        out["version_check"] = "historical"
        out["version_error"] = int(not cites_deprecated)
    elif exposed_deprecated:
        out["version_check"] = "current_with_deprecated_in_context"
        out["version_error"] = int(cites_deprecated)
    out["cites_deprecated"] = cites_deprecated
    return out


def _avg(rows: list[dict], key: str) -> tuple[float | None, int]:
    vals = [r[key] for r in rows if r.get(key) is not None]
    return (round(mean(vals), 4) if vals else None, len(vals))


def aggregate_generation(rows: list[dict]) -> dict:
    ok = [r for r in rows if r["status"] == "ok"]
    ans = [r for r in ok if r["answerable"]]
    una = [r for r in ok if not r["answerable"]]
    answered_ans = [r for r in ans if not r["abstained"]]
    answered_all = [r for r in ok if not r["abstained"]]

    def metric(subset, key):
        v, n = _avg(subset, key)
        return {"value": v, "n": n}

    status_counts: dict[str, int] = {}
    for r in rows:
        status_counts[r["status"]] = status_counts.get(r["status"], 0) + 1
    abst = [r for r in ok if r["abstained"]]
    return {
        "status_counts": status_counts,
        "n_ok": len(ok),
        "answerable": {
            "n": len(ans),
            "answered": len(answered_ans),
            "abstained_gate": sum(1 for r in ans if r["abstain_cause"] == "gate"),
            "abstained_llm": sum(1 for r in ans if r["abstain_cause"] == "llm"),
            "over_abstention": sum(r.get("over_abstention", 0) for r in ans),
            "abstained_with_incomplete_evidence": sum(
                r.get("abstained_with_incomplete_evidence", 0) for r in ans
            ),
            "answered_with_incomplete_evidence": sum(
                r.get("answered_with_incomplete_evidence", 0) for r in ans
            ),
            "over_abstention_rate": round(
                sum(r.get("over_abstention", 0) for r in ans) / len(ans), 4
            )
            if ans
            else None,
        },
        "unanswerable": {
            "n": len(una),
            "abstained_gate": sum(1 for r in una if r["abstain_cause"] == "gate"),
            "abstained_llm": sum(1 for r in una if r["abstain_cause"] == "llm"),
            "improper_answers": sum(r.get("improper_answer", 0) for r in una),
            "improper_answer_rate": round(
                sum(r.get("improper_answer", 0) for r in una) / len(una), 4
            )
            if una
            else None,
        },
        "answered_answerable": {
            "required_facts_coverage": metric(answered_ans, "required_facts_coverage"),
            "all_required_facts": metric(answered_ans, "all_required_facts"),
            "forbidden_present": metric(answered_ans, "forbidden_present"),
            "citation_precision": metric(answered_ans, "citation_precision"),
            "cited_evidence_recall": metric(answered_ans, "cited_evidence_recall"),
        },
        "citations_all_answered": {
            "n_answered": len(answered_all),
            "citation_validity": metric(answered_all, "citation_validity"),
            "answers_with_invalid_citations": sum(
                1 for r in answered_all if r.get("n_invalid_citations", 0) > 0
            ),
            "uncited_answers": sum(r.get("uncited_answer", 0) for r in answered_all),
        },
        "version_selection": {
            "checked": [r["qid"] for r in ans if "version_error" in r],
            "errors": [r["qid"] for r in ans if r.get("version_error") == 1],
            "temporal_rule_disagreements": [
                r["qid"] for r in ans if r.get("temporal_rule_agrees") is False
            ],
        },
        "abstention_causes": {
            "gate": sum(1 for r in abst if r["abstain_cause"] == "gate"),
            "llm": sum(1 for r in abst if r["abstain_cause"] == "llm"),
        },
        "errors": {
            "format_errors": status_counts.get("format_error", 0),
            "api_errors": status_counts.get("api_error", 0),
            "not_run": status_counts.get("not_run", 0),
            "consistency_issues": sum(1 for r in answered_all if r.get("consistency_issues")),
        },
    }
