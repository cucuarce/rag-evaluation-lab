"""Calibración del umbral del gate. Usa SOLO el split calibration (nunca eval).

Regla (fijada antes de mirar resultados de generación):
  s_ans = scores de gate de las preguntas respondibles de calibración
  s_una = scores de las no respondibles
  - Si max(s_una) < min(s_ans) (separables): umbral = punto medio entre ambos.
  - Si no son separables: umbral = min(s_ans) (no bloquear ninguna respondible de
    calibración); el gate prioriza no sobre-abstenerse y la abstención del LLM es la
    segunda línea.
  Abstención por gate si score < umbral.

Con 8 respondibles y 2 no respondibles este umbral es frágil: el reporte lo dice y la
evaluación mide sus efectos (sobre-abstención y respuestas indebidas) en eval.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from rag_lab.config import resolve_path
from rag_lab.corpus import load_corpus
from rag_lab.evaluation.labels import load_labels
from rag_lab.generation.gate import gate_score
from rag_lab.hashing import sha256_file, sha256_json
from rag_lab.runner import _read_jsonl, split_paths

SCORE_TYPES = {
    "dense": "cosine_top1",
    "hybrid": "max_dense_cosine_in_topk",
}
RULE = "midpoint(max_unanswerable, min_answerable) si separables; si no, min_answerable"


def compute_threshold(answerable: list[float], unanswerable: list[float]) -> tuple[float, bool]:
    if not answerable:
        raise ValueError("se necesita al menos una pregunta respondible para calibrar")
    lo = min(answerable)
    if unanswerable and max(unanswerable) < lo:
        return round((max(unanswerable) + lo) / 2, 6), True
    return round(lo, 6), False


def calibrate_gate(calibration_run_dir: Path) -> dict:
    manifest = json.loads((calibration_run_dir / "manifest.json").read_text(encoding="utf-8"))
    if manifest["split"] != "calibration":
        raise ValueError(
            f"el gate solo se calibra con el split calibration (recibido: {manifest['split']})"
        )
    method = manifest["config"]["retrieval"]["method"]
    _, labels_path = split_paths("calibration")
    docs = load_corpus(resolve_path(manifest["config"]["corpus_dir"]))
    labels = load_labels(labels_path, docs)
    rows = _read_jsonl(calibration_run_dir / "retrieval_results.jsonl")
    per_q = []
    for r in rows:
        per_q.append(
            {
                "qid": r["qid"],
                "answerable": labels[r["qid"]].answerable,
                "score": gate_score(r["results"], method),
            }
        )
    ans = [p["score"] for p in per_q if p["answerable"] and p["score"] is not None]
    una = [p["score"] for p in per_q if not p["answerable"] and p["score"] is not None]
    threshold, separable = compute_threshold(ans, una)
    for p in per_q:
        p["blocked"] = p["score"] is None or p["score"] < threshold
    report = {
        "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "calibration_split": "calibration",
        "retrieval_run_name": manifest["run_name"],
        "method": method,
        "index_id": manifest["index_id"],
        "retrieval_config_hash": manifest["config_hash"],
        "score_type": SCORE_TYPES[method],
        "rule": RULE,
        "threshold": threshold,
        "separable_on_calibration": separable,
        "n_answerable": len(ans),
        "n_unanswerable": len(una),
        "min_answerable": round(min(ans), 6),
        "max_unanswerable": round(max(una), 6) if una else None,
        "calibration_blocked_answerable": sum(p["blocked"] for p in per_q if p["answerable"]),
        "calibration_blocked_unanswerable": sum(p["blocked"] for p in per_q if not p["answerable"]),
        "per_question": per_q,
        "calibration_sha256": sha256_json(
            {
                "labels": sha256_file(labels_path),
                "retrieval_results": sha256_file(calibration_run_dir / "retrieval_results.jsonl"),
            }
        ),
        "warning": "Calibrado con n=10 (8 respondibles, 2 no respondibles): umbral frágil, "
        "no es una estimación estadística confiable.",
    }
    return report
