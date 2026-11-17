"""Retrievers con interfaz común. Reciben SOLO el texto de la pregunta.

Reglas de ranking (documentadas en docs/metrics.md):

Dense
  1. Chroma (HNSW, espacio coseno) propone `candidate_pool` candidatos (búsqueda aproximada).
  2. Cada candidato se re-puntúa de forma exacta: coseno = producto punto en float64 entre
     embeddings normalizados.
  3. Orden: score redondeado a `score_decimals` descendente; desempate por chunk_id ascendente.

BM25 (componente léxico de hybrid)
  - BM25Okapi (rank_bm25, k1=1.5, b=0.75, epsilon=0.25) sobre `embed_text` tokenizado.
  - Solo entran al ranking chunks con score > 0 (al menos un término en común).
  - Mismo orden: score redondeado desc, chunk_id asc.

Hybrid (RRF)
  - Los scores dense y BM25 NO son comparables, así que solo se usan los rangos.
  - rrf(c) = Σ_{lista ∋ c} 1 / (rrf_k + rango_lista(c)), con rangos 1-based, sobre el top
    `candidate_pool` de cada lista. Un chunk ausente de una lista no suma por ella.
  - Orden: rrf redondeado desc; desempate por mejor rango individual asc; luego chunk_id asc.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

import numpy as np

from rag_lab.config import RetrievalConfig
from rag_lab.index import LoadedIndex
from rag_lab.text import tokenize

BM25_PARAMS = {"k1": 1.5, "b": 0.75, "epsilon": 0.25}


@dataclass(frozen=True)
class RetrievedChunk:
    rank: int
    chunk_id: str
    doc_id: str
    start: int
    end: int
    status: str
    score: float
    details: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return dict(self.__dict__)


class Retriever(Protocol):
    name: str
    score_type: str

    def retrieve(self, query: str, k: int) -> list[RetrievedChunk]: ...


def _order(scores: dict[str, float], decimals: int) -> list[tuple[str, float]]:
    return sorted(scores.items(), key=lambda kv: (-round(kv[1], decimals), kv[0]))


class DenseRetriever:
    name = "dense"
    score_type = "cosine"

    def __init__(self, index: LoadedIndex, embedder, cfg: RetrievalConfig):
        self.index = index
        self.embedder = embedder
        self.cfg = cfg

    def embed_query(self, query: str) -> np.ndarray:
        return self.embedder.encode_queries([query])[0]

    def _score(self, ids: list[str], q: np.ndarray) -> list[tuple[str, float]]:
        scores = self.index.vectors(ids).astype(np.float64) @ q.astype(np.float64)
        return _order(dict(zip(ids, scores.tolist(), strict=True)), self.cfg.score_decimals)

    def rank_candidates(self, q: np.ndarray) -> list[tuple[str, float]]:
        """Candidatos vía HNSW de Chroma, re-puntuados de forma exacta con embeddings.npy."""
        n = min(self.cfg.candidate_pool, self.index.collection.count())
        res = self.index.collection.query(query_embeddings=[q], n_results=n, include=[])
        return self._score(list(res["ids"][0]), q)

    def rank_exact(self, q: np.ndarray) -> list[tuple[str, float]]:
        """Búsqueda exhaustiva sobre todas las embeddings (diagnóstico del ANN)."""
        return self._score([c.chunk_id for c in self.index.chunks], q)

    def retrieve(self, query: str, k: int) -> list[RetrievedChunk]:
        ranked = self.rank_candidates(self.embed_query(query))[:k]
        return [
            _make(self.index, r, cid, s, {"dense_rank": r, "dense_score": s})
            for r, (cid, s) in enumerate(ranked, start=1)
        ]


class BM25Ranker:
    def __init__(self, index: LoadedIndex, cfg: RetrievalConfig):
        from rank_bm25 import BM25Okapi

        self.cfg = cfg
        self.ids = [c.chunk_id for c in index.chunks]
        self.bm25 = BM25Okapi([tokenize(c.embed_text) for c in index.chunks], **BM25_PARAMS)

    def rank(self, query: str) -> list[tuple[str, float]]:
        scores = self.bm25.get_scores(tokenize(query))
        positive = {cid: float(s) for cid, s in zip(self.ids, scores, strict=True) if s > 0}
        return _order(positive, self.cfg.score_decimals)


class HybridRetriever:
    name = "hybrid"
    score_type = "rrf"

    def __init__(self, dense: DenseRetriever, bm25: BM25Ranker, cfg: RetrievalConfig):
        self.dense = dense
        self.bm25 = bm25
        self.cfg = cfg

    def retrieve(self, query: str, k: int) -> list[RetrievedChunk]:
        pool = self.cfg.candidate_pool
        dense_list = self.dense.rank_candidates(self.dense.embed_query(query))[:pool]
        bm25_list = self.bm25.rank(query)[:pool]
        fused = rrf_fuse(
            {"dense": dense_list, "bm25": bm25_list}, self.cfg.rrf_k, self.cfg.score_decimals
        )
        dense_info = {cid: (r, s) for r, (cid, s) in enumerate(dense_list, start=1)}
        bm25_info = {cid: (r, s) for r, (cid, s) in enumerate(bm25_list, start=1)}
        out = []
        for rank, (cid, score) in enumerate(fused[:k], start=1):
            d, b = dense_info.get(cid), bm25_info.get(cid)
            details = {
                "dense_rank": d[0] if d else None,
                "dense_score": d[1] if d else None,
                "bm25_rank": b[0] if b else None,
                "bm25_score": b[1] if b else None,
                "rrf_score": score,
            }
            out.append(_make(self.dense.index, rank, cid, score, details))
        return out


def rrf_fuse(
    lists: dict[str, list[tuple[str, float]]], rrf_k: int, decimals: int
) -> list[tuple[str, float]]:
    scores: dict[str, float] = {}
    best: dict[str, int] = {}
    for ranked in lists.values():
        for r, (cid, _) in enumerate(ranked, start=1):
            scores[cid] = scores.get(cid, 0.0) + 1.0 / (rrf_k + r)
            best[cid] = min(best.get(cid, r), r)
    return sorted(scores.items(), key=lambda kv: (-round(kv[1], decimals), best[kv[0]], kv[0]))


def _make(index: LoadedIndex, rank: int, cid: str, score: float, details: dict) -> RetrievedChunk:
    c = index.by_id[cid]
    return RetrievedChunk(
        rank=rank,
        chunk_id=cid,
        doc_id=c.doc_id,
        start=c.start,
        end=c.end,
        status=c.status,
        score=score,
        details=details,
    )


def build_retriever(index: LoadedIndex, embedder, cfg: RetrievalConfig) -> Retriever:
    dense = DenseRetriever(index, embedder, cfg)
    if cfg.method == "dense":
        return dense
    return HybridRetriever(dense, BM25Ranker(index, cfg), cfg)
