"""Ejecución de una evaluación de retrieval en dos fases separadas.

Fase 1 (retrieve_split): lee SOLO questions.jsonl y produce retrieval_results.jsonl.
          No recibe ni conoce la ruta de labels.jsonl.
Fase 2 (score_run): une resultados con labels.jsonl y calcula métricas.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from rag_lab.config import PROJECT_ROOT, ExperimentConfig, relative_to_root, resolve_path
from rag_lab.corpus import load_corpus
from rag_lab.hashing import sha256_file
from rag_lab.questions import load_questions
from rag_lab.retrieval import BM25_PARAMS, Retriever

SPLITS = ("eval", "calibration")


def split_paths(split: str) -> tuple[Path, Path]:
    if split not in SPLITS:
        raise ValueError(f"split inválido: {split}")
    base = PROJECT_ROOT / "data" / split
    return base / "questions.jsonl", base / "labels.jsonl"


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def retrieve_split(questions_path: Path, retriever: Retriever, k: int) -> list[dict]:
    """Fase 1. Solo depende de las preguntas y del retriever."""
    rows = []
    for q in load_questions(questions_path):
        results = retriever.retrieve(q.question, k)
        rows.append(
            {
                "qid": q.qid,
                "question": q.question,
                "retriever": retriever.name,
                "score_type": retriever.score_type,
                "k": k,
                "results": [r.to_dict() for r in results],
            }
        )
    return rows


def run_retrieval(
    cfg: ExperimentConfig, index, retriever: Retriever, split: str, out_dir: Path
) -> Path:
    questions_path, _ = split_paths(split)
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = retrieve_split(questions_path, retriever, cfg.retrieval.k)
    _write_jsonl(out_dir / "retrieval_results.jsonl", rows)
    from rag_lab.manifest import environment

    manifest = {
        "run_name": cfg.name,
        "split": split,
        "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "config_path": relative_to_root(cfg.source_path) if cfg.source_path else None,
        "config": cfg.to_dict(),
        "config_hash": cfg.config_hash(),
        "index_id": index.index_id,
        "index_manifest": index.manifest,
        "questions_sha256": sha256_file(questions_path),
        "n_questions": len(rows),
        "bm25_params": BM25_PARAMS if cfg.retrieval.method == "hybrid" else None,
        "environment": environment(),
    }
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return out_dir


def score_run(run_dir: Path) -> dict:
    """Fase 2: une resultados y etiquetas."""
    from rag_lab.evaluation.labels import load_labels
    from rag_lab.evaluation.metrics import aggregate, score_question
    from rag_lab.retrieval import RetrievedChunk

    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    split = manifest["split"]
    _, labels_path = split_paths(split)
    docs = load_corpus(resolve_path(manifest["config"]["corpus_dir"]))
    labels = load_labels(labels_path, docs)
    deprecated = {d.doc_id for d in docs.values() if d.status == "deprecated"}
    tau = manifest["config"]["evaluation"]["span_coverage_threshold"]

    rows = _read_jsonl(run_dir / "retrieval_results.jsonl")
    if {r["qid"] for r in rows} != set(labels):
        raise ValueError("Los qids de los resultados no coinciden con labels.jsonl")

    per_question = []
    for r in rows:
        label = labels[r["qid"]]
        ranked = [RetrievedChunk(**x) for x in r["results"]]
        base = {
            "qid": r["qid"],
            "category": label.category,
            "answerable": label.answerable,
            "retrieved": [x.chunk_id for x in ranked],
            "top1_score": ranked[0].score if ranked else None,
        }
        if label.answerable:
            base.update(score_question(ranked, label, tau, deprecated).to_dict())
        per_question.append(base)

    answerable = [p for p in per_question if p["answerable"]]
    summary = {
        "run_name": manifest["run_name"],
        "split": split,
        "k": manifest["config"]["retrieval"]["k"],
        "method": manifest["config"]["retrieval"]["method"],
        "span_coverage_threshold": tau,
        "labels_sha256": sha256_file(labels_path),
        "n_questions": len(per_question),
        "n_answerable": len(answerable),
        "n_unanswerable": len(per_question) - len(answerable),
        "metrics": aggregate(answerable),
        "note": "Métricas de retrieval solo sobre preguntas respondibles; las no respondibles "
        "se evalúan en la Etapa 2 (abstención).",
    }
    _write_jsonl(run_dir / "per_question.jsonl", per_question)
    (run_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return summary
