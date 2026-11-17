from __future__ import annotations

import pytest

from rag_lab.evaluation.gen_metrics import (
    aggregate_generation,
    fact_present,
    score_generation_row,
)
from tests.conftest import label, span

DEPRECATED = {"old"}


@pytest.mark.parametrize(
    ("fact", "answer", "present"),
    [
        ("30 días", "Tiene 30 dias corridos.", True),
        ("30 días", "Tiene treinta días.", True),  # números escritos
        ("tres veces", "Reintenta 3 veces.", True),
        ("5", "El bloqueo dura 15 minutos.", False),  # no matchea dentro de 15
        ("5", "Después de 5 intentos.", True),
        ("USD 99 ", "Cuesta USD 99,9 por mes.", False),  # no matchea 99,9
        ("USD 99 ", "Cuesta USD 99 por mes.", True),
        ("99,9%", "SLA de 99,9%.", True),
        ("saldo a favor", "Se acredita como SALDO A FAVOR.", True),
        ("no tienen SLA contractual", "No tiene SLA contractual.", False),  # límite léxico
    ],
)
def test_fact_matching(fact, answer, present):
    assert fact_present(fact, answer) is present


def _ctx(*chunks):
    return [
        {"chunk_id": cid, "doc_id": doc, "start": s, "end": e, "status": st}
        for cid, doc, s, e, st in chunks
    ]


NEW = ("new#0", "new", 0, 100, "active")
OLD = ("old#0", "old", 0, 100, "deprecated")


def _lab(gold_doc="new", forbidden=(), required=("30 días",), answerable=True, distr=None):
    lab = label([[span(gold_doc, 10, 20)]], distractors=distr)
    from dataclasses import replace

    if not answerable:
        return replace(lab, answerable=False, gold=(), category="unanswerable")
    return replace(lab, required_facts=tuple(required), forbidden_facts=tuple(forbidden))


def _gen(answer, cited, ctx, abstained=False, cause=None, invalid=()):
    return {
        "qid": "t1",
        "status": "ok",
        "temporal_scope": {"kind": "current"},
        "context": ctx,
        "abstained": abstained,
        "abstain_cause": cause,
        "answer": answer,
        "cited_chunk_ids": cited,
        "llm": {
            "parsed": {
                "citations_raw": [f"S{i}" for i in range(len(cited))] + list(invalid),
                "invalid_citations": list(invalid),
                "consistency_issues": [],
            }
        },
    }


def test_current_question_citing_deprecated_is_a_version_error():
    ctx = _ctx(OLD, NEW)
    row = score_generation_row(
        _gen("Son 14 días.", ["old#0"], ctx), _lab(forbidden=("14 días",)), 0.5, DEPRECATED
    )
    assert row["version_check"] == "current_with_deprecated_in_context"
    assert row["version_error"] == 1 and row["forbidden_present"] == 1
    assert row["citation_precision"] == 0.0 and row["required_facts_coverage"] == 0.0


def test_current_question_answered_from_active_doc():
    row = score_generation_row(
        _gen("Son 30 días.", ["new#0"], _ctx(OLD, NEW)), _lab(), 0.5, DEPRECATED
    )
    assert row["version_error"] == 0 and row["citation_precision"] == 1.0
    assert row["all_required_facts"] == 1 and row["cited_evidence_recall"] == 1.0


def test_historical_question_must_cite_deprecated_version():
    lab = _lab(gold_doc="old", required=("14 días",))
    ok = score_generation_row(
        _gen("Eran 14 días.", ["old#0"], _ctx(NEW, OLD)), lab, 0.5, DEPRECATED
    )
    bad = score_generation_row(
        _gen("Son 30 días.", ["new#0"], _ctx(NEW, OLD)), lab, 0.5, DEPRECATED
    )
    assert ok["label_temporal_kind"] == "historical" and ok["version_error"] == 0
    assert bad["version_error"] == 1
    assert ok["temporal_rule_agrees"] is False  # la regla dijo "current" en este ejemplo


def test_abstention_on_answerable_with_complete_evidence_is_over_abstention():
    row = score_generation_row(
        _gen(None, [], _ctx(NEW), abstained=True, cause="gate"), _lab(), 0.5, DEPRECATED
    )
    assert row["over_abstention"] == 1


def test_abstention_with_missing_evidence_is_not_over_abstention():
    row = score_generation_row(
        _gen(None, [], _ctx(OLD), abstained=True, cause="llm"), _lab(), 0.5, DEPRECATED
    )
    assert row["over_abstention"] == 0 and row["abstained_with_incomplete_evidence"] == 1


def test_answering_unanswerable_is_improper():
    lab = _lab(answerable=False)
    answered = score_generation_row(_gen("Sí.", ["new#0"], _ctx(NEW)), lab, 0.5, DEPRECATED)
    abstained = score_generation_row(
        _gen(None, [], _ctx(NEW), abstained=True, cause="llm"), lab, 0.5, DEPRECATED
    )
    assert answered["improper_answer"] == 1 and abstained["correct_abstention"] == 1


def test_citation_validity_counts_invalid_citations():
    row = score_generation_row(
        _gen("Son 30 días.", ["new#0"], _ctx(NEW), invalid=("S9",)), _lab(), 0.5, DEPRECATED
    )
    assert row["citation_validity"] == 0.5 and row["n_invalid_citations"] == 1


def test_aggregate_counts_errors_and_abstentions():
    rows = [
        {
            "status": "ok",
            "answerable": True,
            "abstained": True,
            "abstain_cause": "gate",
            "over_abstention": 1,
        },
        {
            "status": "ok",
            "answerable": False,
            "abstained": False,
            "abstain_cause": None,
            "improper_answer": 1,
        },
        {"status": "format_error", "answerable": True},
        {"status": "api_error", "answerable": True},
    ]
    agg = aggregate_generation(rows)
    assert agg["answerable"]["over_abstention"] == 1
    assert agg["unanswerable"]["improper_answers"] == 1
    assert agg["errors"]["format_errors"] == 1 and agg["errors"]["api_errors"] == 1
