from __future__ import annotations

import json

import pytest

from rag_lab.evaluation.labels import load_labels, resolve_quote
from rag_lab.runner import split_paths
from rag_lab.validate import validate_data


def test_real_datasets_are_valid(cfg_a):
    report = validate_data(cfg_a)
    assert report["n_documents"] == 12
    assert report["splits"]["eval"]["n_questions"] == 40
    assert report["splits"]["calibration"]["n_questions"] == 10
    assert report["splits"]["eval"]["categories"] == {
        "single": 14,
        "multi_hop": 8,
        "distractor": 8,
        "unanswerable": 10,
    }


def test_every_gold_quote_resolves_to_exact_text(docs):
    for split in ("eval", "calibration"):
        labels = load_labels(split_paths(split)[1], docs)
        for lab in labels.values():
            for req in lab.gold:
                for s in req.alternatives:
                    assert docs[s.doc_id].body[s.start : s.end] == s.quote


def test_missing_quote_is_rejected(docs):
    with pytest.raises(ValueError, match="no aparece"):
        resolve_quote(docs, "sla", "texto que no existe", "t")


def test_ambiguous_quote_is_rejected(docs):
    with pytest.raises(ValueError, match="más de una vez"):
        resolve_quote(docs, "limites-api", "requests por minuto", "t")


def test_unknown_document_is_rejected(docs):
    with pytest.raises(ValueError, match="inexistente"):
        resolve_quote(docs, "no-existe", "x", "t")


def _base_row(**over):
    row = {
        "qid": "x1",
        "category": "single",
        "answerable": True,
        "gold_evidence": [
            {
                "id": "ev1",
                "spans": [
                    {
                        "doc_id": "sla",
                        "quote": "Los planes Starter y Pro no tienen SLA contractual.",
                    }
                ],
            }
        ],
        "distractor_evidence": [],
        "reference_answer": "r",
        "required_facts": [],
        "forbidden_facts": [],
        "notes": "",
    }
    row.update(over)
    return row


@pytest.mark.parametrize(
    ("override", "message"),
    [
        ({"extra": 1}, "claves"),
        ({"category": "otra"}, "categoría"),
        ({"answerable": False}, "inconsistente"),
        ({"gold_evidence": []}, "sin evidencia"),
        ({"category": "multi_hop"}, "multi_hop"),
        ({"category": "distractor"}, "distractor"),
    ],
)
def test_invalid_labels_are_rejected(tmp_path, docs, override, message):
    p = tmp_path / "labels.jsonl"
    p.write_text(json.dumps(_base_row(**override)) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match=message):
        load_labels(p, docs)


def test_unanswerable_with_evidence_is_rejected(tmp_path, docs):
    row = _base_row(category="unanswerable", answerable=False)
    p = tmp_path / "labels.jsonl"
    p.write_text(json.dumps(row) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="no respondible"):
        load_labels(p, docs)
