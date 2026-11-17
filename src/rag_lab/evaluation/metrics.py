"""Métricas de retrieval. Funciones puras: no cargan modelos ni índices.

Definiciones (ver docs/metrics.md). Sea R_k la lista de los k chunks recuperados, en orden,
y τ = span_coverage_threshold.

- Un chunk c *cubre* un span s si están en el mismo documento y
  |[c.start, c.end) ∩ [s.start, s.end)| / |s| >= τ.
- c *satisface* un requisito g si cubre alguna de sus citas alternativas.
- c es *gold* si satisface algún requisito de la pregunta.
- c es *distractor* si cubre algún span distractor Y no es gold (si un mismo chunk contiene
  la evidencia correcta y la incorrecta, cuenta como gold).

Por pregunta respondible:
- hit@k        = 1 si algún c ∈ R_k es gold.
- recall@k     = |{g : algún c ∈ R_k satisface g}| / |G|.
- complete@k   = 1 si recall@k == 1 (todas las evidencias necesarias recuperadas).
- rr@k         = 1 / rango del primer chunk gold en R_k; 0 si no hay. MRR@k = promedio.
- distractor@k (solo si hay spans distractores etiquetados) = 1 si hay un chunk distractor en
  R_k con rango menor al del primer chunk gold, o si hay un distractor y ningún gold.
  Más bajo es mejor.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from statistics import mean
from typing import Protocol

from rag_lab.evaluation.labels import Label, Span

EPS = 1e-12


class RetrievedLike(Protocol):
    chunk_id: str
    doc_id: str
    start: int
    end: int
    status: str


def overlap(a_start: int, a_end: int, b_start: int, b_end: int) -> int:
    return max(0, min(a_end, b_end) - max(a_start, b_start))


def covers(chunk: RetrievedLike, span: Span, tau: float) -> bool:
    if chunk.doc_id != span.doc_id or len(span) == 0:
        return False
    return overlap(chunk.start, chunk.end, span.start, span.end) / len(span) >= tau - EPS


@dataclass(frozen=True)
class QuestionMetrics:
    hit: int
    recall: float
    complete: int
    rr: float
    first_gold_rank: int | None
    satisfied: tuple[str, ...]
    missing: tuple[str, ...]
    gold_ranks: tuple[int, ...]
    distractor_ranks: tuple[int, ...]
    distractor: int | None  # None = no aplica
    deprecated_in_topk: int | None  # None = no aplica

    def to_dict(self) -> dict:
        d = dict(self.__dict__)
        d["satisfied"] = list(self.satisfied)
        d["missing"] = list(self.missing)
        d["gold_ranks"] = list(self.gold_ranks)
        d["distractor_ranks"] = list(self.distractor_ranks)
        return d


def score_question(
    ranked: Sequence[RetrievedLike],
    label: Label,
    tau: float,
    deprecated_docs: set[str],
) -> QuestionMetrics:
    if not label.answerable:
        raise ValueError("score_question solo aplica a preguntas respondibles")
    satisfied: set[str] = set()
    gold_ranks: list[int] = []
    distractor_ranks: list[int] = []
    for rank, chunk in enumerate(ranked, start=1):
        is_gold = False
        for req in label.gold:
            if any(covers(chunk, s, tau) for s in req.alternatives):
                satisfied.add(req.id)
                is_gold = True
        if is_gold:
            gold_ranks.append(rank)
        elif any(covers(chunk, d, tau) for d in label.distractors):
            distractor_ranks.append(rank)

    req_ids = [r.id for r in label.gold]
    recall = len(satisfied) / len(req_ids)
    first_gold = gold_ranks[0] if gold_ranks else None

    distractor: int | None = None
    if label.distractors:
        distractor = int(
            bool(distractor_ranks) and (first_gold is None or distractor_ranks[0] < first_gold)
        )

    gold_docs = {s.doc_id for r in label.gold for s in r.alternatives}
    deprecated_in_topk: int | None = None
    if not gold_docs & deprecated_docs:
        deprecated_in_topk = int(any(c.doc_id in deprecated_docs for c in ranked))

    return QuestionMetrics(
        hit=int(bool(gold_ranks)),
        recall=recall,
        complete=int(len(satisfied) == len(req_ids)),
        rr=1.0 / first_gold if first_gold else 0.0,
        first_gold_rank=first_gold,
        satisfied=tuple(r for r in req_ids if r in satisfied),
        missing=tuple(r for r in req_ids if r not in satisfied),
        gold_ranks=tuple(gold_ranks),
        distractor_ranks=tuple(distractor_ranks),
        distractor=distractor,
        deprecated_in_topk=deprecated_in_topk,
    )


METRIC_KEYS = ("hit", "recall", "complete", "rr", "distractor", "deprecated_in_topk")


def aggregate(rows: list[dict]) -> dict:
    """rows: dicts con 'category' y las claves de METRIC_KEYS (None = no aplica)."""

    def summarize(subset: list[dict]) -> dict:
        out: dict = {"n": len(subset)}
        for key in METRIC_KEYS:
            vals = [r[key] for r in subset if r.get(key) is not None]
            name = "mrr" if key == "rr" else key
            out[name] = round(mean(vals), 4) if vals else None
            out[f"{name}_n"] = len(vals)
        return out

    by_cat = {}
    for cat in sorted({r["category"] for r in rows}):
        by_cat[cat] = summarize([r for r in rows if r["category"] == cat])
    return {"overall": summarize(rows), "by_category": by_cat}
