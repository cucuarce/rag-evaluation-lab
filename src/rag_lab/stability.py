"""Verificación de estabilidad del ranking en el entorno actual.

No se asume determinismo: se mide.
1. Re-encoding: se recarga el modelo y se re-codifica el corpus; se compara contra
   embeddings.npy (hash bit a bit y diferencia máxima absoluta). También se informa cuánto
   difieren las embeddings que devuelve Chroma de las que se le entregaron.
2. Repetición: se ejecuta el retrieval completo `repeats` veces, cada una con el modelo
   recargado, y se comparan los top-k (ids y scores).
3. ANN vs exacto: se compara el ranking dense obtenido vía candidatos HNSW de Chroma contra
   una búsqueda exhaustiva sobre todas las embeddings.
4. Fragilidad: se informa el menor margen de score entre posiciones adyacentes del top-(k+1)
   dense exacto; márgenes muy chicos indican rankings que podrían invertirse ante ruido
   numérico en otro hardware.
"""

from __future__ import annotations

from itertools import pairwise

import numpy as np

from rag_lab.config import ExperimentConfig
from rag_lab.embeddings import Embedder
from rag_lab.index import embeddings_digest, load_index
from rag_lab.questions import load_questions
from rag_lab.retrieval import DenseRetriever, build_retriever
from rag_lab.runner import split_paths

NEAR_TIE = 1e-4


def run_stability(cfg: ExperimentConfig, split: str, repeats: int) -> dict:
    if repeats < 2:
        raise ValueError("repeats debe ser >= 2")
    index = load_index(cfg)
    questions = load_questions(split_paths(split)[0])
    k = cfg.retrieval.k
    chroma_ids, chroma_emb = index.chroma_embeddings()
    chroma_roundtrip = float(np.max(np.abs(chroma_emb - index.vectors(chroma_ids))))

    reencode = []
    runs: list[dict[str, list[tuple[str, float]]]] = []
    ann_mismatch: list[str] = []
    ann_pool_mismatch: list[str] = []
    gaps: dict[str, float] = {}
    for _ in range(repeats):
        embedder = Embedder(cfg.embedding)
        fresh = embedder.encode_passages([c.embed_text for c in index.chunks])
        reencode.append(
            {
                "bitwise_equal_to_index": embeddings_digest(fresh)
                == index.manifest["embeddings_sha256"],
                "max_abs_diff": float(np.max(np.abs(fresh - index.embeddings))),
            }
        )
        retriever = build_retriever(index, embedder, cfg.retrieval)
        dense = DenseRetriever(index, embedder, cfg.retrieval)
        result = {}
        for q in questions:
            result[q.qid] = [(r.chunk_id, r.score) for r in retriever.retrieve(q.question, k)]
            if not runs:  # diagnósticos ANN y de márgenes: una vez alcanza
                qv = dense.embed_query(q.question)
                approx = dense.rank_candidates(qv)
                exact = dense.rank_exact(qv)
                if [c for c, _ in approx[:k]] != [c for c, _ in exact[:k]]:
                    ann_mismatch.append(q.qid)
                pool = cfg.retrieval.candidate_pool
                if {c for c, _ in approx[:pool]} != {c for c, _ in exact[:pool]}:
                    ann_pool_mismatch.append(q.qid)
                top = [s for _, s in exact[: k + 1]]
                gaps[q.qid] = min(abs(a - b) for a, b in pairwise(top))
        runs.append(result)

    base = runs[0]
    differing = sorted(
        {
            qid
            for r in runs[1:]
            for qid in base
            if [c for c, _ in r[qid]] != [c for c, _ in base[qid]]
        }
    )
    max_score_diff = max(
        (
            abs(s1 - s2)
            for r in runs[1:]
            for qid in base
            for (_, s1), (_, s2) in zip(r[qid], base[qid], strict=True)
        ),
        default=0.0,
    )
    near_ties = sorted(q for q, g in gaps.items() if g < NEAR_TIE)
    return {
        "run_name": cfg.name,
        "method": cfg.retrieval.method,
        "split": split,
        "k": k,
        "repeats": repeats,
        "index_id": index.index_id,
        "reencode": reencode,
        "chroma_roundtrip_max_abs_diff": chroma_roundtrip,
        "topk_identical_across_repeats": not differing,
        "questions_with_different_topk": differing,
        "max_abs_score_diff_across_repeats": max_score_diff,
        "ann_vs_exact_topk_mismatch": ann_mismatch,
        "ann_vs_exact_pool_mismatch": ann_pool_mismatch,
        "dense_min_adjacent_gap_topk1": {
            "min": min(gaps.values()),
            "median": float(np.median(list(gaps.values()))),
            "near_tie_threshold": NEAR_TIE,
            "questions_with_near_ties": near_ties,
        },
        "scope": "Misma máquina, mismo proceso, modelo recargado en cada repetición. "
        "No garantiza igualdad en otro hardware/SO.",
    }
