"""Construcción y carga del índice (ChromaDB persistente + chunks.jsonl).

El índice es *direccionado por contenido*: su id es un hash del corpus, de la configuración
de chunking y de la de embeddings. A y B comparten el mismo índice si comparten esos
parámetros, y un corpus modificado nunca reutiliza un índice viejo.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime

import numpy as np

from rag_lab.chunking import Chunk, chunk_corpus
from rag_lab.config import ExperimentConfig
from rag_lab.corpus import load_corpus
from rag_lab.hashing import sha256_bytes, sha256_dir, sha256_json

CHUNKER_VERSION = "1"
INDEX_FORMAT = "2"  # 2: embeddings.npy propia para re-scoring exacto


def compute_index_id(cfg: ExperimentConfig) -> tuple[str, str]:
    corpus_hash = sha256_dir(cfg.corpus_dir)
    payload = {
        "corpus": corpus_hash,
        "chunker_version": CHUNKER_VERSION,
        "index_format": INDEX_FORMAT,
        **cfg.index_params(),
    }
    return sha256_json(payload)[:16], corpus_hash


def _chroma_client(cfg: ExperimentConfig):
    import chromadb
    from chromadb.config import Settings

    return chromadb.PersistentClient(
        path=str(cfg.index_dir / "chroma"),
        settings=Settings(anonymized_telemetry=False, allow_reset=False),
    )


def _collection_name(index_id: str) -> str:
    return f"kb-{index_id}"


def _meta(c: Chunk) -> dict:
    return {
        "doc_id": c.doc_id,
        "start": c.start,
        "end": c.end,
        "section": c.section,
        "status": c.status,
        "version": c.version,
        "effective_date": c.effective_date,
        "superseded_by": c.superseded_by or "",
    }


def embeddings_digest(emb: np.ndarray) -> str:
    return sha256_bytes(np.ascontiguousarray(emb, dtype=np.float32).tobytes())


def build_index(cfg: ExperimentConfig, embedder, force: bool = False) -> dict:
    index_id, corpus_hash = compute_index_id(cfg)
    out_dir = cfg.index_dir / index_id
    client = _chroma_client(cfg)
    name = _collection_name(index_id)
    existing = {c.name if hasattr(c, "name") else c for c in client.list_collections()}
    if name in existing and (out_dir / "index_manifest.json").exists() and not force:
        return json.loads((out_dir / "index_manifest.json").read_text(encoding="utf-8"))
    if name in existing:
        client.delete_collection(name)

    docs = load_corpus(cfg.corpus_dir)
    chunks = chunk_corpus(docs, cfg.chunking.max_chars)
    token_counts = embedder.count_tokens(
        [cfg.embedding.passage_prefix + c.embed_text for c in chunks]
    )
    if max(token_counts) > embedder.max_seq_length:
        raise ValueError(
            f"Un chunk excede el límite del modelo ({max(token_counts)} > "
            f"{embedder.max_seq_length} tokens) y sería truncado. Reducí chunking.max_chars."
        )
    emb = embedder.encode_passages([c.embed_text for c in chunks])

    collection = client.create_collection(
        name=name,
        embedding_function=None,
        configuration={"hnsw": {"space": "cosine"}},
        metadata={"index_id": index_id},
    )
    collection.add(
        ids=[c.chunk_id for c in chunks],
        embeddings=emb,
        documents=[c.embed_text for c in chunks],
        metadatas=[_meta(c) for c in chunks],
    )

    out_dir.mkdir(parents=True, exist_ok=True)
    # Copia propia de las embeddings: Chroma puede alterar los últimos bits al almacenarlas
    # (en espacio coseno), así que el re-scoring exacto usa esta matriz.
    np.save(out_dir / "embeddings.npy", emb)
    with (out_dir / "chunks.jsonl").open("w", encoding="utf-8", newline="\n") as fh:
        for c in chunks:
            fh.write(json.dumps(c.to_dict(), ensure_ascii=False) + "\n")
    import chromadb

    manifest = {
        "index_id": index_id,
        "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "corpus_hash": corpus_hash,
        "n_documents": len(docs),
        "n_deprecated_documents": sum(d.status == "deprecated" for d in docs.values()),
        "n_chunks": len(chunks),
        "chunker_version": CHUNKER_VERSION,
        "index_format": INDEX_FORMAT,
        "chunking": cfg.index_params()["chunking"],
        "embedding": cfg.index_params()["embedding"],
        "embedding_dim": int(emb.shape[1]),
        "max_chunk_tokens": int(max(token_counts)),
        "model_max_seq_length": embedder.max_seq_length,
        "chunk_chars": {
            "min": min(len(c.text) for c in chunks),
            "max": max(len(c.text) for c in chunks),
        },
        "embeddings_sha256": embeddings_digest(emb),
        "chroma_collection": name,
        "chroma_version": chromadb.__version__,
        "chroma_space": "cosine",
        "includes_deprecated": True,
    }
    (out_dir / "index_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return manifest


@dataclass
class LoadedIndex:
    index_id: str
    manifest: dict
    chunks: list[Chunk]
    by_id: dict[str, Chunk]
    collection: object
    embeddings: np.ndarray  # alineada con `chunks`
    row: dict[str, int]  # chunk_id -> fila en `embeddings`

    def vectors(self, ids: list[str]) -> np.ndarray:
        return self.embeddings[[self.row[i] for i in ids]]

    def chroma_embeddings(self) -> tuple[list[str], np.ndarray]:
        """Embeddings tal como las devuelve Chroma (solo diagnóstico)."""
        got = self.collection.get(include=["embeddings"])
        return list(got["ids"]), np.asarray(got["embeddings"], dtype=np.float32)


def load_index(cfg: ExperimentConfig) -> LoadedIndex:
    index_id, _ = compute_index_id(cfg)
    out_dir = cfg.index_dir / index_id
    manifest_path = out_dir / "index_manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(
            f"No existe el índice {index_id} para el corpus/config actuales. "
            f"Ejecutá: rag-lab index --config {cfg.source_path}"
        )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    chunks = []
    for line in (out_dir / "chunks.jsonl").read_text(encoding="utf-8").splitlines():
        chunks.append(Chunk(**json.loads(line)))
    emb = np.load(out_dir / "embeddings.npy")
    if embeddings_digest(emb) != manifest["embeddings_sha256"]:
        raise RuntimeError(
            "embeddings.npy no coincide con el hash del manifiesto; reindexá con --force"
        )
    collection = _chroma_client(cfg).get_collection(_collection_name(index_id))
    if collection.count() != len(chunks) or emb.shape[0] != len(chunks):
        raise RuntimeError(
            "Chroma / embeddings.npy no coinciden con chunks.jsonl; reindexá con --force"
        )
    return LoadedIndex(
        index_id=index_id,
        manifest=manifest,
        chunks=chunks,
        by_id={c.chunk_id: c for c in chunks},
        collection=collection,
        embeddings=emb,
        row={c.chunk_id: i for i, c in enumerate(chunks)},
    )
