"""Respuestas únicas de las generaciones guardadas, con contexto y trazabilidad a A/B.

Lee solo `generations.jsonl`, `gen_manifest.json` y el manifiesto de retrieval de cada
corrida, más el corpus (para reconstruir el texto de los fragmentos con el mismo chunking
determinístico del índice). No lee etiquetas ni regenera respuestas.

Una respuesta única = (qid, texto de la respuesta, chunks citados, contexto completo en
orden). Si A y B produjeron exactamente lo mismo con el mismo contexto (e02, e21, e32 en la
Etapa 2) es una sola respuesta con dos ocurrencias. Si el texto coincide pero el contexto
difiere, son respuestas distintas, porque el respaldo en "contexto completo" puede cambiar.
"""

from __future__ import annotations

import json
from pathlib import Path

from rag_lab.chunking import chunk_corpus
from rag_lab.config import PROJECT_ROOT, resolve_path
from rag_lab.corpus import load_corpus
from rag_lab.generation.context import ChunkStore
from rag_lab.hashing import sha256_file, sha256_json
from rag_lab.runner import _read_jsonl


def answer_id(qid: str, answer: str, cited: list[str], context: list[str]) -> str:
    return sha256_json(
        {"qid": qid, "answer": answer, "cited_chunk_ids": cited, "context_chunk_ids": context}
    )[:16]


def _rel(p: Path) -> str:
    p = p.resolve()
    return p.relative_to(PROJECT_ROOT).as_posix() if p.is_relative_to(PROJECT_ROOT) else str(p)


def collect_unique_answers(gen_dirs: list[Path]) -> tuple[list[dict], dict]:
    """Devuelve (respuestas únicas ordenadas por qid/answer_id, procedencia)."""
    by_id: dict[str, dict] = {}
    provenance = []
    stores: dict[tuple, ChunkStore] = {}
    for gen_dir in gen_dirs:
        gm = json.loads((gen_dir / "gen_manifest.json").read_text(encoding="utf-8"))
        rm = json.loads(
            (resolve_path(gm["retrieval_run"]) / "manifest.json").read_text(encoding="utf-8")
        )
        corpus_dir = resolve_path(rm["config"]["corpus_dir"])
        max_chars = rm["config"]["chunking"]["max_chars"]
        key = (str(corpus_dir), max_chars)
        if key not in stores:
            docs = load_corpus(corpus_dir)
            chunks = {c.chunk_id: c.to_dict() for c in chunk_corpus(docs, max_chars)}
            stores[key] = ChunkStore(chunks, docs)
        store = stores[key]
        run = gm["retrieval_run_name"]
        provenance.append(
            {
                "run": run,
                "gen_dir": _rel(gen_dir),
                "generation": gm["generation_config"]["name"],
                "split": gm["split"],
                "index_id": gm["index_id"],
                "generations_sha256": sha256_file(gen_dir / "generations.jsonl"),
            }
        )
        for g in _read_jsonl(gen_dir / "generations.jsonl"):
            if g["status"] != "ok" or g["abstained"]:
                continue
            ctx_ids = [c["chunk_id"] for c in g["context"]]
            built = store.build(ctx_ids)
            for b, c in zip(built, g["context"], strict=True):
                if (b.cite_id, b.start, b.end) != (c["cite_id"], c["start"], c["end"]):
                    raise ValueError(f"{run}/{g['qid']}: el chunk {b.chunk_id} no coincide")
            aid = answer_id(g["qid"], g["answer"], g["cited_chunk_ids"], ctx_ids)
            occ = {"run": run, "gen_dir": _rel(gen_dir), "prompt_sha256": g["prompt_sha256"]}
            if aid in by_id:
                by_id[aid]["occurrences"].append(occ)
                continue
            cid_to_cite = {b.chunk_id: b.cite_id for b in built}
            by_id[aid] = {
                "answer_id": aid,
                "qid": g["qid"],
                "question": g["question"],
                "temporal_scope": g["temporal_scope"],
                "answer": g["answer"],
                "cited_cite_ids": [cid_to_cite[c] for c in g["cited_chunk_ids"]],
                "cited_chunk_ids": g["cited_chunk_ids"],
                "context": [
                    {
                        "cite_id": b.cite_id,
                        "chunk_id": b.chunk_id,
                        "doc_id": b.doc_id,
                        "title": b.title,
                        "section": b.section,
                        "version": b.version,
                        "status": b.status,
                        "vigencia": b.vigencia(),
                        "text": b.text,
                    }
                    for b in built
                ],
                "occurrences": [occ],
            }
    answers = sorted(by_id.values(), key=lambda a: (a["qid"], a["answer_id"]))
    return answers, {"sources": provenance}
