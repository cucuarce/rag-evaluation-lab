from __future__ import annotations

import pytest

from rag_lab.evaluation.metrics import aggregate, covers, overlap, score_question
from tests.conftest import FakeChunk, label, span

TAU = 0.5


# --- relevancia span -> chunk: casos límite ------------------------------------------


def test_overlap_basic():
    assert overlap(0, 10, 5, 15) == 5
    assert overlap(0, 10, 10, 20) == 0  # intervalos semiabiertos: se tocan pero no se solapan
    assert overlap(0, 10, 20, 30) == 0


@pytest.mark.parametrize(
    ("chunk", "expected"),
    [
        (FakeChunk("c", "d", 100, 200), True),  # contiene el span completo
        (FakeChunk("c", "d", 150, 300), True),  # cubre exactamente 50% (150..200 de 100..200)
        (FakeChunk("c", "d", 151, 300), False),  # cubre 49%
        (FakeChunk("c", "d", 0, 100), False),  # termina justo donde empieza el span
        (FakeChunk("c", "otro", 100, 200), False),  # mismo rango, otro documento
        (FakeChunk("c", "d", 120, 180), True),  # chunk dentro del span, cubre 60%
    ],
)
def test_covers_threshold_edges(chunk, expected):
    assert covers(chunk, span("d", 100, 200), TAU) is expected


def test_covers_with_full_threshold_requires_full_containment():
    s = span("d", 100, 200)
    assert covers(FakeChunk("c", "d", 100, 200), s, 1.0)
    assert not covers(FakeChunk("c", "d", 101, 200), s, 1.0)


# --- métricas por pregunta ------------------------------------------------------------


def test_single_hit_and_reciprocal_rank():
    lab = label([[span("d", 10, 20)]])
    ranked = [FakeChunk("x", "d", 100, 200), FakeChunk("g", "d", 0, 50)]
    m = score_question(ranked, lab, TAU, set())
    assert (m.hit, m.recall, m.complete, m.rr, m.first_gold_rank) == (1, 1.0, 1, 0.5, 2)


def test_miss_gives_zero():
    lab = label([[span("d", 10, 20)]])
    m = score_question([FakeChunk("x", "d", 100, 200)], lab, TAU, set())
    assert (m.hit, m.recall, m.complete, m.rr, m.first_gold_rank) == (0, 0.0, 0, 0.0, None)


def test_multi_hop_requires_all_evidence():
    lab = label([[span("a", 0, 10)], [span("b", 0, 10)]], category="multi_hop")
    partial = score_question([FakeChunk("1", "a", 0, 50)], lab, TAU, set())
    assert (partial.hit, partial.recall, partial.complete) == (1, 0.5, 0)
    assert partial.missing == ("ev2",)
    full = score_question([FakeChunk("1", "a", 0, 50), FakeChunk("2", "b", 0, 50)], lab, TAU, set())
    assert (full.recall, full.complete) == (1.0, 1)


def test_two_requirements_in_same_chunk_both_satisfied():
    lab = label([[span("a", 0, 10)], [span("a", 20, 30)]], category="multi_hop")
    m = score_question([FakeChunk("1", "a", 0, 50)], lab, TAU, set())
    assert m.complete == 1


def test_alternative_spans_satisfy_requirement():
    lab = label([[span("a", 0, 10), span("b", 0, 10)]])
    m = score_question([FakeChunk("1", "b", 0, 50)], lab, TAU, set())
    assert m.recall == 1.0


def test_distractor_ranked_above_gold():
    lab = label([[span("v3", 0, 10)]], distractors=[span("v2", 0, 10)])
    m = score_question([FakeChunk("d", "v2", 0, 50), FakeChunk("g", "v3", 0, 50)], lab, TAU, set())
    assert m.distractor == 1
    m2 = score_question([FakeChunk("g", "v3", 0, 50), FakeChunk("d", "v2", 0, 50)], lab, TAU, set())
    assert m2.distractor == 0


def test_distractor_without_gold_counts():
    lab = label([[span("v3", 0, 10)]], distractors=[span("v2", 0, 10)])
    m = score_question([FakeChunk("d", "v2", 0, 50)], lab, TAU, set())
    assert (m.hit, m.distractor) == (0, 1)


def test_chunk_with_gold_and_distractor_counts_as_gold():
    lab = label([[span("p", 0, 10)]], distractors=[span("p", 20, 30)])
    m = score_question([FakeChunk("both", "p", 0, 50)], lab, TAU, set())
    assert (m.hit, m.distractor, m.distractor_ranks) == (1, 0, ())


def test_distractor_not_applicable_without_labels():
    m = score_question([FakeChunk("g", "a", 0, 50)], label([[span("a", 0, 10)]]), TAU, set())
    assert m.distractor is None


def test_unanswerable_is_rejected():
    lab = label([[span("a", 0, 10)]])
    lab = lab.__class__(**{**lab.__dict__, "answerable": False, "category": "unanswerable"})
    with pytest.raises(ValueError):
        score_question([], lab, TAU, set())


def test_aggregate_ignores_not_applicable_values():
    rows = [
        {
            "category": "single",
            "hit": 1,
            "recall": 1.0,
            "complete": 1,
            "rr": 1.0,
            "distractor": None,
            "deprecated_in_topk": 0,
        },
        {
            "category": "distractor",
            "hit": 1,
            "recall": 1.0,
            "complete": 1,
            "rr": 0.5,
            "distractor": 1,
            "deprecated_in_topk": 1,
        },
    ]
    agg = aggregate(rows)
    assert agg["overall"]["mrr"] == 0.75
    assert agg["overall"]["distractor"] == 1
    assert agg["overall"]["distractor_n"] == 1
    assert agg["by_category"]["single"]["distractor"] is None
