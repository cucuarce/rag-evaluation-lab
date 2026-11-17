from __future__ import annotations

from dataclasses import replace

import pytest

from rag_lab.chunking import chunk_corpus
from rag_lab.corpus import validate_versioning
from rag_lab.evaluation.labels import load_labels
from rag_lab.evaluation.metrics import score_question
from rag_lab.runner import split_paths
from tests.conftest import FakeChunk, label, span


def test_refund_policy_versions_are_linked(docs):
    v2, v3 = docs["politica-reembolsos-v2"], docs["politica-reembolsos-v3"]
    assert v2.status == "deprecated" and v3.status == "active"
    assert v2.superseded_by == v3.doc_id and v3.supersedes == v2.doc_id
    assert v2.end_date < v3.effective_date
    assert [d.doc_id for d in docs.values() if d.status == "deprecated"] == [v2.doc_id]


def test_deprecated_chunks_are_indexed_with_status(docs, cfg_a):
    chunks = chunk_corpus(docs, cfg_a.chunking.max_chars)
    dep = [c for c in chunks if c.doc_id == "politica-reembolsos-v2"]
    assert dep and all(c.status == "deprecated" for c in dep)
    assert all(c.superseded_by == "politica-reembolsos-v3" for c in dep)


@pytest.mark.parametrize(
    "mutation",
    [
        {"superseded_by": None},
        {"end_date": None},
        {"superseded_by": "sla"},  # sucesor que no declara supersedes recíproco
    ],
)
def test_inconsistent_versioning_is_rejected(docs, mutation):
    bad = dict(docs)
    bad["politica-reembolsos-v2"] = replace(docs["politica-reembolsos-v2"], **mutation)
    with pytest.raises(ValueError):
        validate_versioning(bad)


def test_active_doc_cannot_be_superseded(docs):
    bad = dict(docs)
    bad["sla"] = replace(docs["sla"], superseded_by="planes-y-precios")
    with pytest.raises(ValueError):
        validate_versioning(bad)


def test_current_policy_questions_label_deprecated_version_as_distractor(docs):
    labels = load_labels(split_paths("eval")[1], docs)
    e06 = labels["e06"]
    assert {s.doc_id for r in e06.gold for s in r.alternatives} == {"politica-reembolsos-v3"}
    assert {d.doc_id for d in e06.distractors} == {"politica-reembolsos-v2"}
    # pregunta histórica: la versión deprecated es la evidencia correcta
    e10 = labels["e10"]
    assert "politica-reembolsos-v2" in {s.doc_id for s in e10.gold[0].alternatives}


def test_deprecated_in_topk_only_applies_when_gold_is_active():
    dep = {"v2"}
    active_q = label([[span("v3", 0, 10)]])
    m = score_question(
        [FakeChunk("g", "v3", 0, 50), FakeChunk("o", "v2", 0, 50, "deprecated")], active_q, 0.5, dep
    )
    assert m.deprecated_in_topk == 1
    historical_q = label([[span("v2", 0, 10)]])
    m2 = score_question([FakeChunk("o", "v2", 0, 50, "deprecated")], historical_q, 0.5, dep)
    assert m2.deprecated_in_topk is None
