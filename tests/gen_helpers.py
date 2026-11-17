"""Fixtures offline para la Etapa 2: corrida de retrieval sintética + índice sin modelo."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

from rag_lab.chunking import chunk_corpus
from rag_lab.config import PROJECT_ROOT, load_config
from rag_lab.corpus import load_corpus
from rag_lab.generation.config import load_generation_config
from rag_lab.generation.providers import GenerationResult

FAKE_CFG = PROJECT_ROOT / "configs" / "gen_fake.toml"
GROQ_CFG = PROJECT_ROOT / "configs" / "gen_groq.toml"
INDEX_ID = "testindex0000000"


def make_retrieval_run(
    tmp: Path, rows: list[tuple[str, str, list[str], float]], method: str = "dense"
) -> tuple[Path, Path]:
    """rows = (qid, question, chunk_ids, top_score). Devuelve (run_dir, index_root)."""
    cfg = load_config(PROJECT_ROOT / "configs" / "a_dense_k5.toml")
    docs = load_corpus(cfg.corpus_dir)
    index_root = tmp / "index"
    idx = index_root / INDEX_ID
    idx.mkdir(parents=True)
    with (idx / "chunks.jsonl").open("w", encoding="utf-8") as fh:
        for c in chunk_corpus(docs, cfg.chunking.max_chars):
            fh.write(json.dumps(c.to_dict(), ensure_ascii=False) + "\n")
    (idx / "index_manifest.json").write_text(json.dumps({"index_id": INDEX_ID}), encoding="utf-8")
    run = tmp / "run"
    run.mkdir()
    out = []
    for qid, question, cids, top in rows:
        results = []
        for i, cid in enumerate(cids, start=1):
            details = {"dense_score": top - 0.01 * (i - 1)} if method == "hybrid" else {}
            results.append(
                {
                    "rank": i,
                    "chunk_id": cid,
                    "doc_id": cid.split("#")[0],
                    "start": 0,
                    "end": 1,
                    "status": "active",
                    "score": top - 0.01 * (i - 1) if method == "dense" else 0.03,
                    "details": details,
                }
            )
        out.append({"qid": qid, "question": question, "results": results})
    (run / "retrieval_results.jsonl").write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in out) + "\n", encoding="utf-8"
    )
    manifest = {
        "run_name": "T_run",
        "split": "eval",
        "config": cfg.to_dict() | {"retrieval": {"method": method, "k": 5}},
        "config_hash": "cfghash",
        "index_id": INDEX_ID,
        "questions_sha256": "qsha",
    }
    (run / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return run, index_root


def write_gate(tmp: Path, threshold: float, method: str = "dense") -> Path:
    p = tmp / "gate.json"
    p.write_text(
        json.dumps(
            {
                "calibration_split": "calibration",
                "retrieval_run_name": "T_run",
                "method": method,
                "index_id": INDEX_ID,
                "retrieval_config_hash": "cfghash",
                "threshold": threshold,
                "score_type": "cosine_top1",
                "rule": "test",
                "calibration_sha256": "x",
            }
        ),
        encoding="utf-8",
    )
    return p


def fake_cfg(**limits):
    cfg = load_generation_config(FAKE_CFG)
    if limits:
        cfg = replace(cfg, limits=replace(cfg.limits, **limits))
    return cfg


def ok_result(payload: dict | str, tokens: int = 100) -> GenerationResult:
    content = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)
    return GenerationResult(
        content=content,
        usage={"prompt_tokens": tokens - 10, "completion_tokens": 10, "total_tokens": tokens},
        latency_s=0.01,
        model_returned="scripted",
    )


class ScriptedGenerator:
    """Devuelve (o lanza) elementos de una lista, en orden. Registra los prompts recibidos."""

    provider = "fake"
    model = "scripted"

    def __init__(self, script):
        self.script = list(script)
        self.prompts: list[str] = []

    def generate(self, messages, schema):
        self.prompts.append(messages[-1]["content"])
        item = self.script.pop(0) if len(self.script) > 1 else self.script[0]
        if isinstance(item, Exception):
            raise item
        return item


ANSWER_S1 = {
    "answer": "Respuesta.",
    "citations": ["S1"],
    "abstain": False,
    "abstain_reason": "none",
}
