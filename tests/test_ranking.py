from __future__ import annotations

from types import SimpleNamespace

from rag_lab.config import RetrievalConfig
from rag_lab.retrieval import BM25Ranker, _order, rrf_fuse
from rag_lab.text import tokenize

CFG = RetrievalConfig(method="hybrid", k=5, candidate_pool=50, rrf_k=60, score_decimals=6)


def test_order_breaks_ties_by_chunk_id():
    assert _order({"b": 0.5, "a": 0.5, "c": 0.9}, 6) == [("c", 0.9), ("a", 0.5), ("b", 0.5)]


def test_order_treats_differences_below_precision_as_ties():
    ranked = _order({"b": 0.5000001, "a": 0.5000000}, 6)
    assert [c for c, _ in ranked] == ["a", "b"]


def test_order_is_independent_of_input_order():
    items = {"x": 0.3, "y": 0.7, "z": 0.3}
    assert _order(items, 6) == _order(dict(reversed(list(items.items()))), 6)


def test_rrf_scores_match_formula():
    fused = dict(
        rrf_fuse(
            {"dense": [("a", 0.9), ("b", 0.8)], "bm25": [("b", 7.0), ("c", 3.0)]},
            rrf_k=60,
            decimals=9,
        )
    )
    assert abs(fused["a"] - 1 / 61) < 1e-12
    assert abs(fused["b"] - (1 / 62 + 1 / 61)) < 1e-12
    assert abs(fused["c"] - 1 / 62) < 1e-12


def test_rrf_uses_ranks_not_raw_scores():
    # Scores BM25 enormes no deben dominar: solo cuenta el rango.
    a = rrf_fuse({"dense": [("x", 0.1), ("y", 0.09)], "bm25": [("y", 1e6), ("x", 1e-6)]}, 60, 9)
    b = rrf_fuse({"dense": [("x", 0.9), ("y", 0.1)], "bm25": [("y", 2.0), ("x", 1.0)]}, 60, 9)
    assert [c for c, _ in a] == [c for c, _ in b]


def test_rrf_tie_broken_by_best_rank_then_chunk_id():
    # p y q: rangos (3,1) y (1,3) -> mismo rrf y mismo mejor rango (1) -> desempate por id.
    # z: rangos (2,2) -> 2/62, apenas menor que 1/61 + 1/63.
    fused = rrf_fuse(
        {"dense": [("q", 1), ("z", 1), ("p", 1)], "bm25": [("p", 1), ("z", 1), ("q", 1)]}, 60, 6
    )
    assert [c for c, _ in fused] == ["p", "q", "z"]
    # a y c: 1/61 cada uno, mejor rango 1 -> id; b: 1/62.
    tie = rrf_fuse({"dense": [("a", 1), ("b", 1)], "bm25": [("c", 1)]}, 60, 6)
    assert [c for c, _ in tie] == ["a", "c", "b"]


def test_tokenize_strips_accents_keeps_numbers_and_drops_stopwords():
    assert tokenize("¿Cuántos días tiene la política de reembolsos?") == [
        "cuantos",
        "dias",
        "politica",
        "reembolsos",
    ]
    assert tokenize("hasta 5.000 facturas y 99,9%") == ["5.000", "facturas", "99,9"]


def _fake_index(texts: dict[str, str]):
    chunks = [SimpleNamespace(chunk_id=cid, embed_text=t) for cid, t in texts.items()]
    return SimpleNamespace(chunks=chunks)


def test_bm25_excludes_chunks_without_term_overlap_and_is_deterministic():
    idx = _fake_index(
        {
            "a": "reembolso de planes mensuales",
            "b": "límites de la API por minuto",
            "c": "seguridad de la cuenta",
            "d": "webhooks y exportaciones",
        }
    )
    ranker = BM25Ranker(idx, CFG)
    r1 = ranker.rank("reembolso mensual")
    assert [c for c, _ in r1] == ["a"]
    assert r1 == ranker.rank("reembolso mensual")
