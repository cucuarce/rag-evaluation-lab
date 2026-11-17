"""Fase 2 de la Etapa 2: une generaciones con etiquetas y compara A vs B."""

from __future__ import annotations

import json
from pathlib import Path

from rag_lab.compare import IncompatibleRuns, sign_test_p
from rag_lab.config import resolve_path
from rag_lab.corpus import load_corpus
from rag_lab.evaluation.gen_metrics import aggregate_generation, score_generation_row
from rag_lab.evaluation.labels import load_labels
from rag_lab.hashing import sha256_file
from rag_lab.runner import _read_jsonl, _write_jsonl, split_paths


def score_generation(gen_dir: Path) -> dict:
    gm = json.loads((gen_dir / "gen_manifest.json").read_text(encoding="utf-8"))
    run_manifest = json.loads(
        (resolve_path(gm["retrieval_run"]) / "manifest.json").read_text(encoding="utf-8")
    )
    _, labels_path = split_paths(gm["split"])
    docs = load_corpus(resolve_path(run_manifest["config"]["corpus_dir"]))
    labels = load_labels(labels_path, docs)
    deprecated = {d.doc_id for d in docs.values() if d.status == "deprecated"}
    tau = run_manifest["config"]["evaluation"]["span_coverage_threshold"]
    gens = _read_jsonl(gen_dir / "generations.jsonl")
    rows = [score_generation_row(g, labels[g["qid"]], tau, deprecated) for g in gens]
    summary = {
        "retrieval_run_name": gm["retrieval_run_name"],
        "generation": gm["generation_config"]["name"],
        "model": gm["generation_config"]["model"]["model"],
        "split": gm["split"],
        "run_status": gm["run_status"],
        "partial_qids": gm["partial_qids"],
        "labels_sha256": sha256_file(labels_path),
        "gate": gm["gate"],
        "metrics": aggregate_generation(rows),
        "calls": gm["counts"],
        "tokens_real": gm["tokens_real"],
        "note": "Métricas léxicas/estructurales. No son faithfulness semántica (Etapa 3).",
    }
    _write_jsonl(gen_dir / "gen_per_question.jsonl", rows)
    (gen_dir / "gen_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return summary


# métrica por pregunta -> True si más alto es mejor
GEN_PAIRED = {
    "required_facts_coverage": True,
    "all_required_facts": True,
    "forbidden_present": False,
    "citation_precision": True,
    "cited_evidence_recall": True,
    "abstained": None,  # se reporta, sin "mejor"
}


def _value(row: dict, key: str):
    if key == "abstained":
        return None if row.get("abstained") is None else int(row["abstained"])
    return row.get(key)


def compare_generation(gen_a: Path, gen_b: Path) -> dict:
    ma = json.loads((gen_a / "gen_manifest.json").read_text(encoding="utf-8"))
    mb = json.loads((gen_b / "gen_manifest.json").read_text(encoding="utf-8"))
    sa = json.loads((gen_a / "gen_summary.json").read_text(encoding="utf-8"))
    sb = json.loads((gen_b / "gen_summary.json").read_text(encoding="utf-8"))
    ga = {k: v for k, v in ma["generation_config"].items() if k != "name"}
    gb = {k: v for k, v in mb["generation_config"].items() if k != "name"}
    checks = {
        "split": (ma["split"], mb["split"]),
        "index_id": (ma["index_id"], mb["index_id"]),
        "questions_sha256": (ma["questions_sha256"], mb["questions_sha256"]),
        "labels_sha256": (sa["labels_sha256"], sb["labels_sha256"]),
        "generation_config": (ga, gb),
        "prompt_template_sha256": (ma["prompt_template_sha256"], mb["prompt_template_sha256"]),
        "answer_schema_sha256": (ma["answer_schema_sha256"], mb["answer_schema_sha256"]),
        "run_status": (ma["run_status"], mb["run_status"]),
        "partial_qids": (ma["partial_qids"], mb["partial_qids"]),
    }
    bad = {k: v for k, v in checks.items() if v[0] != v[1]}
    if bad:
        raise IncompatibleRuns(f"Generaciones no comparables: {sorted(bad)}")
    if ma["run_status"] != "complete":
        raise IncompatibleRuns("Solo se comparan corridas completas")

    ra = {r["qid"]: r for r in _read_jsonl(gen_a / "gen_per_question.jsonl")}
    rb = {r["qid"]: r for r in _read_jsonl(gen_b / "gen_per_question.jsonl")}
    paired = {}
    for key, higher in GEN_PAIRED.items():
        a_better = b_better = ties = n = 0
        diffs = []
        for qid in sorted(ra):
            va, vb = _value(ra[qid], key), _value(rb[qid], key)
            if va is None or vb is None:
                continue
            n += 1
            if va == vb:
                ties += 1
                continue
            diffs.append(qid)
            if higher is None:
                continue
            if (va > vb) == higher:
                a_better += 1
            else:
                b_better += 1
        paired[key] = {
            "n_pairs": n,
            "a_better": a_better if higher is not None else None,
            "b_better": b_better if higher is not None else None,
            "ties": ties,
            "differs_in": diffs,
            "sign_test_p": sign_test_p(a_better, b_better) if higher is not None else None,
        }
    return {
        "run_a": ma["retrieval_run_name"],
        "run_b": mb["retrieval_run_name"],
        "generation": ma["generation_config"]["name"],
        "shared": {k: v[0] for k, v in checks.items() if k != "generation_config"},
        "summary_a": sa["metrics"],
        "summary_b": sb["metrics"],
        "gate_a": sa["gate"],
        "gate_b": sb["gate"],
        "paired": paired,
        "note": "Pares solo donde ambas corridas tienen valor (p. ej. ambas respondieron). "
        "n chico: el test de signo no es evidencia fuerte. Los umbrales de gate difieren por "
        "diseño (cada configuración se calibra por separado).",
    }
