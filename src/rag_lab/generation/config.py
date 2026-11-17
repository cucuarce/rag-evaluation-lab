"""Configuración de generación (TOML). Independiente de las configs de retrieval A/B.

Las configs A y B de la Etapa 1 no se modifican: la generación consume una corrida de
retrieval ya hecha (runs/<split>/<run>/retrieval_results.jsonl).
"""

from __future__ import annotations

import tomllib
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path

from rag_lab.hashing import sha256_json

PROVIDERS = {"groq", "fake"}
REASONING_EFFORTS = {"low", "medium", "high"}


@dataclass(frozen=True)
class ModelConfig:
    provider: str
    model: str
    temperature: float
    max_completion_tokens: int
    reasoning_effort: str | None
    seed: int | None


@dataclass(frozen=True)
class LimitsConfig:
    timeout_s: float
    max_retries: int  # reintentos ante errores transitorios (no incluye el intento inicial)
    max_retry_after_s: float  # 429 con retry-after mayor -> se aborta la corrida (cuota)
    backoff_base_s: float
    max_concurrency: int
    min_interval_s: float  # separación mínima entre inicios de llamadas
    max_calls: int  # presupuesto de llamadas reales (no cacheadas) por comando
    max_total_tokens: int  # presupuesto de tokens reales por comando
    max_consecutive_failures: int


@dataclass(frozen=True)
class GenerationConfig:
    name: str
    model: ModelConfig
    limits: LimitsConfig
    prompt_version: str
    reference_date: str  # "hoy" para la regla temporal (fijo para reproducibilidad)
    gate_enabled: bool
    source_path: Path | None = None

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "model": asdict(self.model),
            "limits": asdict(self.limits),
            "prompt_version": self.prompt_version,
            "reference_date": self.reference_date,
            "gate_enabled": self.gate_enabled,
        }

    def request_params(self) -> dict:
        """Parámetros que afectan la respuesta del modelo (entran en la clave de caché)."""
        m = self.model
        return {
            "provider": m.provider,
            "model": m.model,
            "temperature": m.temperature,
            "max_completion_tokens": m.max_completion_tokens,
            "reasoning_effort": m.reasoning_effort,
            "seed": m.seed,
        }

    def config_hash(self) -> str:
        return sha256_json(self.to_dict())


def load_generation_config(path: str | Path) -> GenerationConfig:
    path = Path(path).resolve()
    with path.open("rb") as fh:
        raw = tomllib.load(fh)
    g = raw["generation"]
    cfg = GenerationConfig(
        name=g["name"],
        model=ModelConfig(**raw["model"]),
        limits=LimitsConfig(**raw["limits"]),
        prompt_version=g["prompt_version"],
        reference_date=g["reference_date"],
        gate_enabled=raw["gate"]["enabled"],
        source_path=path,
    )
    validate_generation_config(cfg)
    return cfg


def validate_generation_config(cfg: GenerationConfig) -> None:
    m, lim = cfg.model, cfg.limits
    if m.provider not in PROVIDERS:
        raise ValueError(f"provider inválido: {m.provider!r} (válidos: {sorted(PROVIDERS)})")
    if not m.model.strip():
        raise ValueError("model no puede estar vacío")
    if not 0.0 <= m.temperature <= 0.5:
        raise ValueError("temperature debe estar en [0, 0.5] (se pide temperatura baja)")
    if not 64 <= m.max_completion_tokens <= 4096:
        raise ValueError("max_completion_tokens fuera de [64, 4096]")
    if m.reasoning_effort is not None and m.reasoning_effort not in REASONING_EFFORTS:
        raise ValueError(f"reasoning_effort inválido: {m.reasoning_effort!r}")
    if not 1 <= lim.timeout_s <= 300:
        raise ValueError("timeout_s fuera de [1, 300]")
    if not 0 <= lim.max_retries <= 5:
        raise ValueError("max_retries fuera de [0, 5] (reintentos acotados)")
    if not 1 <= lim.max_concurrency <= 4:
        raise ValueError("max_concurrency fuera de [1, 4]")
    if lim.max_calls < 1 or lim.max_total_tokens < 1:
        raise ValueError("el presupuesto de llamadas y tokens debe ser positivo")
    if lim.min_interval_s < 0 or lim.backoff_base_s < 0 or lim.max_retry_after_s < 0:
        raise ValueError("intervalos negativos")
    if lim.max_consecutive_failures < 1:
        raise ValueError("max_consecutive_failures debe ser >= 1")
    date.fromisoformat(cfg.reference_date)
