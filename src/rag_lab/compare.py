"""Comparación pareada de dos corridas sobre el mismo dataset.

La comparación se rechaza si las corridas no comparten: índice (corpus + chunking +
embeddings), hash de preguntas, hash de etiquetas, split, k y umbral τ.
"""

from __future__ import annotations

import json
from math import comb
from pathlib import Path
from statistics import mean

# métrica -> True si "más alto es mejor"
PAIRED_METRICS = {"hit": True, "recall": True, "complete": True, "rr": True, "distractor": False}


class IncompatibleRuns(ValueError):
    pass


def _load(run_dir: Path) -> tuple[dict, dict, dict[str, dict]]:
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    summary_path = run_dir / "summary.json"
    if not summary_path.exists():
        raise FileNotFoundError(f"{run_dir} no tiene summary.json (falta puntuar la corrida)")
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    rows = [
        json.loads(x)
        for x in (run_dir / "per_question.jsonl").read_text(encoding="utf-8").splitlines()
        if x.strip()
    ]
    return manifest, summary, {r["qid"]: r for r in rows}


def check_compatible(ma: dict, sa: dict, mb: dict, sb: dict) -> dict:
    checks = {
        "index_id": (ma["index_id"], mb["index_id"]),
        "questions_sha256": (ma["questions_sha256"], mb["questions_sha256"]),
        "labels_sha256": (sa["labels_sha256"], sb["labels_sha256"]),
        "split": (ma["split"], mb["split"]),
        "k": (ma["config"]["retrieval"]["k"], mb["config"]["retrieval"]["k"]),
        "span_coverage_threshold": (sa["span_coverage_threshold"], sb["span_coverage_threshold"]),
    }
    bad = {k: v for k, v in checks.items() if v[0] != v[1]}
    if bad:
        raise IncompatibleRuns(f"Corridas no comparables: {bad}")
    return {k: v[0] for k, v in checks.items()}


def sign_test_p(wins: int, losses: int) -> float | None:
    """Test de signo exacto bilateral sobre pares no empatados."""
    n = wins + losses
    if n == 0:
        return None
    tail = sum(comb(n, i) for i in range(0, min(wins, losses) + 1)) / 2**n
    return round(min(1.0, 2 * tail), 4)


def compare_runs(run_a: Path, run_b: Path) -> dict:
    ma, sa, ra = _load(run_a)
    mb, sb, rb = _load(run_b)
    shared = check_compatible(ma, sa, mb, sb)
    if set(ra) != set(rb):
        raise IncompatibleRuns("Las corridas no tienen el mismo conjunto de preguntas")

    per_question = []
    stats = {m: {"a_better": 0, "b_better": 0, "ties": 0, "n": 0} for m in PAIRED_METRICS}
    for qid in sorted(ra):
        a, b = ra[qid], rb[qid]
        row = {
            "qid": qid,
            "category": a["category"],
            "answerable": a["answerable"],
            "topk_identical": a["retrieved"] == b["retrieved"],
            "topk_same_set": set(a["retrieved"]) == set(b["retrieved"]),
            "a_retrieved": a["retrieved"],
            "b_retrieved": b["retrieved"],
        }
        if a["answerable"]:
            for m, higher_better in PAIRED_METRICS.items():
                va, vb = a.get(m), b.get(m)
                row[f"a_{m}"], row[f"b_{m}"] = va, vb
                if va is None or vb is None:
                    continue
                s = stats[m]
                s["n"] += 1
                if va == vb:
                    s["ties"] += 1
                elif (vb > va) == higher_better:
                    s["b_better"] += 1
                else:
                    s["a_better"] += 1
            row["a_missing"], row["b_missing"] = a["missing"], b["missing"]
        per_question.append(row)

    for m, s in stats.items():
        s["sign_test_p"] = sign_test_p(s["a_better"], s["b_better"])
        a_vals = [r[f"a_{m}"] for r in per_question if r.get(f"a_{m}") is not None]
        b_vals = [r[f"b_{m}"] for r in per_question if r.get(f"b_{m}") is not None]
        s["mean_a"] = round(mean(a_vals), 4) if a_vals else None
        s["mean_b"] = round(mean(b_vals), 4) if b_vals else None
        s["delta_b_minus_a"] = round(s["mean_b"] - s["mean_a"], 4) if a_vals and b_vals else None
        s["higher_is_better"] = PAIRED_METRICS[m]

    changed = [
        r
        for r in per_question
        if r["answerable"] and any(r.get(f"a_{m}") != r.get(f"b_{m}") for m in PAIRED_METRICS)
    ]
    return {
        "run_a": {
            "name": ma["run_name"],
            "method": ma["config"]["retrieval"]["method"],
            "dir": run_a.as_posix(),
            "created_at": ma["created_at"],
        },
        "run_b": {
            "name": mb["run_name"],
            "method": mb["config"]["retrieval"]["method"],
            "dir": run_b.as_posix(),
            "created_at": mb["created_at"],
        },
        "shared": shared,
        "summary_a": sa["metrics"],
        "summary_b": sb["metrics"],
        "paired": stats,
        "n_topk_identical": sum(r["topk_identical"] for r in per_question),
        "n_questions": len(per_question),
        "questions_with_metric_change": [r["qid"] for r in changed],
        "per_question": per_question,
        "caveat": "n pequeño: diferencias de pocas preguntas no son concluyentes. El test de signo "
        "ignora empates y no corrige por comparaciones múltiples.",
    }
