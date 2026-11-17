"""Carga y validación de configuraciones de experimento (TOML, stdlib)."""

from __future__ import annotations

import tomllib
from dataclasses import asdict, dataclass
from pathlib import Path

from rag_lab.hashing import sha256_json

PROJECT_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class ChunkingConfig:
    max_chars: int


@dataclass(frozen=True)
class EmbeddingConfig:
    model: str
    revision: str
    query_prefix: str
    passage_prefix: str
    normalize: bool
    batch_size: int
    device: str


@dataclass(frozen=True)
class RetrievalConfig:
    method: str  # "dense" | "hybrid"
    k: int
    candidate_pool: int
    rrf_k: int
    score_decimals: int


@dataclass(frozen=True)
class EvaluationConfig:
    span_coverage_threshold: float


@dataclass(frozen=True)
class ExperimentConfig:
    name: str
    corpus_dir: Path
    index_dir: Path
    chunking: ChunkingConfig
    embedding: EmbeddingConfig
    retrieval: RetrievalConfig
    evaluation: EvaluationConfig
    source_path: Path | None = None

    def index_params(self) -> dict:
        """Parámetros que determinan el índice (compartido entre A y B)."""
        return {"chunking": asdict(self.chunking), "embedding": asdict(self.embedding)}

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "corpus_dir": relative_to_root(self.corpus_dir),
            "chunking": asdict(self.chunking),
            "embedding": asdict(self.embedding),
            "retrieval": asdict(self.retrieval),
            "evaluation": asdict(self.evaluation),
        }

    def config_hash(self) -> str:
        return sha256_json(self.to_dict())


VALID_METHODS = {"dense", "hybrid"}


def _resolve(path: str) -> Path:
    p = Path(path)
    return p if p.is_absolute() else PROJECT_ROOT / p


def relative_to_root(path: Path) -> str:
    """Ruta portable (relativa a la raíz del proyecto) para hashes y manifiestos."""
    try:
        return path.resolve().relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def resolve_path(path: str) -> Path:
    return _resolve(path)


def load_config(path: str | Path) -> ExperimentConfig:
    path = Path(path).resolve()
    with path.open("rb") as fh:
        raw = tomllib.load(fh)
    cfg = ExperimentConfig(
        name=raw["experiment"]["name"],
        corpus_dir=_resolve(raw["paths"]["corpus_dir"]),
        index_dir=_resolve(raw["paths"]["index_dir"]),
        chunking=ChunkingConfig(**raw["chunking"]),
        embedding=EmbeddingConfig(**raw["embedding"]),
        retrieval=RetrievalConfig(**raw["retrieval"]),
        evaluation=EvaluationConfig(**raw["evaluation"]),
        source_path=path,
    )
    validate_config(cfg)
    return cfg


def validate_config(cfg: ExperimentConfig) -> None:
    r = cfg.retrieval
    if r.method not in VALID_METHODS:
        raise ValueError(f"retrieval.method inválido: {r.method!r}")
    if r.k < 1 or r.candidate_pool < r.k:
        raise ValueError("Se requiere 1 <= k <= candidate_pool")
    if r.rrf_k < 1:
        raise ValueError("rrf_k debe ser >= 1")
    if not 0 < cfg.evaluation.span_coverage_threshold <= 1:
        raise ValueError("span_coverage_threshold debe estar en (0, 1]")
    if len(cfg.embedding.revision) != 40:
        raise ValueError("embedding.revision debe ser un commit SHA completo (40 caracteres)")
    if not cfg.embedding.normalize:
        raise ValueError(
            "Se requiere normalize=true: el ranking asume similitud coseno = producto punto"
        )
