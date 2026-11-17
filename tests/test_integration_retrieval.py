"""Tests de integración con el modelo real y el índice construido.

Se saltean si el índice no existe (ejecutar antes `rag-lab index`). Marcados como `model`.
"""

from __future__ import annotations

import pytest

from rag_lab.index import load_index

pytestmark = pytest.mark.model


@pytest.fixture(scope="module")
def loaded(cfg_a):
    try:
        index = load_index(cfg_a)
    except FileNotFoundError:
        pytest.skip("índice no construido; ejecutá `rag-lab index`")
    from rag_lab.embeddings import Embedder

    return index, Embedder(cfg_a.embedding)


def test_embeddings_are_normalized(loaded):
    import numpy as np

    index, _ = loaded
    norms = np.linalg.norm(index.embeddings.astype(np.float64), axis=1)
    assert np.allclose(norms, 1.0, atol=1e-5)


def test_chunks_fit_model_window(loaded):
    index, _ = loaded
    assert index.manifest["max_chunk_tokens"] <= index.manifest["model_max_seq_length"]


@pytest.mark.parametrize("cfg_name", ["cfg_a", "cfg_b"])
def test_ranking_is_stable_within_process(loaded, request, cfg_name):
    from rag_lab.retrieval import build_retriever

    cfg = request.getfixturevalue(cfg_name)
    index, embedder = loaded
    retriever = build_retriever(index, embedder, cfg.retrieval)
    q = "¿Cuántos días tiene un cliente para pedir el reembolso de una suscripción mensual nueva?"
    r1 = [(r.chunk_id, r.score) for r in retriever.retrieve(q, 5)]
    r2 = [(r.chunk_id, r.score) for r in retriever.retrieve(q, 5)]
    assert r1 == r2
    assert len(r1) == 5


def test_dense_ann_candidates_match_exact_search(loaded, cfg_a):
    from rag_lab.questions import load_questions
    from rag_lab.retrieval import DenseRetriever
    from rag_lab.runner import split_paths

    index, embedder = loaded
    dense = DenseRetriever(index, embedder, cfg_a.retrieval)
    for q in load_questions(split_paths("eval")[0]):
        qv = dense.embed_query(q.question)
        assert dense.rank_candidates(qv)[:5] == dense.rank_exact(qv)[:5], q.qid
