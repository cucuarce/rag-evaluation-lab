"""Métricas de acuerdo con etiquetas sintéticas (no son resultados de ningún juez real)."""

from __future__ import annotations

import pytest

from rag_lab.faithfulness.agreement import cohen_kappa, compare_labels, wilson

S, P, U, IC, X = (
    "supported",
    "partially_supported",
    "unsupported",
    "insufficient_context",
    "judge_unverifiable",
)


def test_wilson_known_values():
    assert wilson(0, 10) == [0.0, 0.2775]
    assert wilson(10, 10) == [0.7225, 1.0]
    assert wilson(5, 10) == [0.2366, 0.7634]
    assert wilson(0, 0) is None


def test_kappa_textbook_example():
    # 2x2: a=20 (S,S), b=5 (S,U), c=10 (U,S), d=15 (U,U); po=0.7, pe=0.5 -> kappa 0.4
    pairs = [(S, S)] * 20 + [(S, U)] * 5 + [(U, S)] * 10 + [(U, U)] * 15
    assert cohen_kappa(pairs) == (0.4, None)


def test_kappa_not_reported_for_tiny_or_degenerate_samples():
    assert cohen_kappa([(S, S)] * 5)[0] is None
    value, note = cohen_kappa([(S, S)] * 12)
    assert value is None and "una sola categoría" in note


def test_confusion_matrix_and_critical_cases():
    ref = {f"c{i}": lab for i, lab in enumerate([S, S, S, P, P, U, U, IC, U, S, P, U])}
    ev = {f"c{i}": lab for i, lab in enumerate([S, S, P, S, P, S, U, IC, X, S, S, U])}
    r = compare_labels(ref, ev, "humano", "juez")
    m = r["confusion_matrix"]["counts"]
    assert m[S] == {S: 3, P: 1, U: 0, IC: 0, X: 0}
    assert m[P] == {S: 2, P: 1, U: 0, IC: 0, X: 0}
    assert m[U] == {S: 1, P: 0, U: 2, IC: 0, X: 1}
    assert m[IC][IC] == 1
    assert r["agreement"]["k"] == 7 and r["n_compared"] == 12
    crit = r["evaluated_supported_reference_not"]
    assert crit["claim_ids"] == ["c10", "c3", "c5"]  # orden de claim_id
    assert crit["n_reference_not_supported"] == 8
    assert {d["reference"] for d in crit["detail"]} == {P, U}
    assert r["evaluated_not_reference_supported"]["claim_ids"] == ["c2"]
    assert "no demuestra confiabilidad" in r["warning"]


def test_missing_claims_are_reported_not_compared():
    r = compare_labels({"a": S, "b": U}, {"a": S, "c": U}, "h", "j")
    assert r["n_compared"] == 1
    assert r["missing_in_evaluated"] == ["b"] and r["missing_in_reference"] == ["c"]


def test_reference_cannot_use_judge_only_label():
    with pytest.raises(ValueError):
        compare_labels({"a": X}, {"a": S}, "h", "j")
