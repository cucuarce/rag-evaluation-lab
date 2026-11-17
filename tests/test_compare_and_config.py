from __future__ import annotations

import json
from pathlib import Path

import pytest

from rag_lab.compare import IncompatibleRuns, compare_runs, sign_test_p


def test_configs_a_and_b_differ_only_in_name_and_method(cfg_a, cfg_b):
    a, b = cfg_a.to_dict(), cfg_b.to_dict()
    assert a["retrieval"].pop("method") == "dense"
    assert b["retrieval"].pop("method") == "hybrid"
    a.pop("name"), b.pop("name")
    assert a == b
    assert cfg_a.index_params() == cfg_b.index_params()
    assert cfg_a.retrieval.k == 5


def test_sign_test_values():
    assert sign_test_p(0, 0) is None
    assert sign_test_p(5, 0) == 0.0625
    assert sign_test_p(1, 1) == 1.0


def _write_run(d: Path, name: str, rows: list[dict], index_id: str = "idx", k: int = 5) -> Path:
    d.mkdir(parents=True)
    manifest = {
        "run_name": name,
        "split": "eval",
        "created_at": "t",
        "index_id": index_id,
        "questions_sha256": "q",
        "config": {"retrieval": {"k": k, "method": name}},
    }
    summary = {"labels_sha256": "l", "span_coverage_threshold": 0.5, "metrics": {}}
    (d / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (d / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
    (d / "per_question.jsonl").write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    return d


def _row(qid, rr, recall=1.0, retrieved=("a",), distractor=None):
    return {
        "qid": qid,
        "category": "single",
        "answerable": True,
        "retrieved": list(retrieved),
        "hit": int(rr > 0),
        "recall": recall,
        "complete": int(recall == 1.0),
        "rr": rr,
        "distractor": distractor,
        "missing": [],
    }


def test_paired_comparison_counts_wins_losses_ties(tmp_path):
    a = _write_run(tmp_path / "a", "dense", [_row("q1", 1.0), _row("q2", 0.5), _row("q3", 1.0)])
    b = _write_run(
        tmp_path / "b",
        "hybrid",
        [_row("q1", 0.5, retrieved=("b",)), _row("q2", 1.0), _row("q3", 1.0)],
    )
    rep = compare_runs(a, b)
    assert (
        rep["paired"]["rr"]["a_better"],
        rep["paired"]["rr"]["b_better"],
        rep["paired"]["rr"]["ties"],
    ) == (1, 1, 1)
    assert rep["n_topk_identical"] == 2
    assert rep["questions_with_metric_change"] == ["q1", "q2"]


def test_lower_is_better_for_distractor(tmp_path):
    a = _write_run(tmp_path / "a", "dense", [_row("q1", 1.0, distractor=1)])
    b = _write_run(tmp_path / "b", "hybrid", [_row("q1", 1.0, distractor=0)])
    assert compare_runs(a, b)["paired"]["distractor"]["b_better"] == 1


@pytest.mark.parametrize("kwargs", [{"index_id": "otro"}, {"k": 3}])
def test_incompatible_runs_are_rejected(tmp_path, kwargs):
    a = _write_run(tmp_path / "a", "dense", [_row("q1", 1.0)])
    b = _write_run(tmp_path / "b", "hybrid", [_row("q1", 1.0)], **kwargs)
    with pytest.raises(IncompatibleRuns):
        compare_runs(a, b)
