"""Embeddings locales con Sentence Transformers, con revisión del modelo fijada."""

from __future__ import annotations

import numpy as np

from rag_lab.config import EmbeddingConfig


class Embedder:
    def __init__(self, cfg: EmbeddingConfig):
        from sentence_transformers import SentenceTransformer  # import diferido: es pesado

        self.cfg = cfg
        self.model = SentenceTransformer(cfg.model, revision=cfg.revision, device=cfg.device)

    @property
    def max_seq_length(self) -> int:
        return int(self.model.max_seq_length)

    def count_tokens(self, texts: list[str]) -> list[int]:
        tok = self.model.tokenizer
        return [len(tok(t, add_special_tokens=True)["input_ids"]) for t in texts]

    def _encode(self, texts: list[str]) -> np.ndarray:
        vecs = self.model.encode(
            texts,
            batch_size=self.cfg.batch_size,
            normalize_embeddings=self.cfg.normalize,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        return np.asarray(vecs, dtype=np.float32)

    def encode_passages(self, texts: list[str]) -> np.ndarray:
        return self._encode([self.cfg.passage_prefix + t for t in texts])

    def encode_queries(self, texts: list[str]) -> np.ndarray:
        return self._encode([self.cfg.query_prefix + t for t in texts])
