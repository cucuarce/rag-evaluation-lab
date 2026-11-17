"""Configuración del juez semántico (Etapa 3B), separada de la de generación.

Reutiliza `LimitsConfig` de la Etapa 2 (caché, presupuesto, ritmo y reintentos se aplican igual).
"""

from __future__ import annotations

import tomllib
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path

from rag_lab.faithfulness.judge_prompt import JUDGE_PROMPT_VERSION
from rag_lab.generation.config import LimitsConfig
from rag_lab.hashing import sha256_json

JUDGE_PROVIDERS = {"groq", "fake"}
JSON_SCHEMA_NAME = "faithfulness_judgment"


@dataclass(frozen=True)
class JudgeModelConfig:
    provider: str
    model: str
    temperature: float
    max_completion_tokens: int
    seed: int | None = None
    include_reasoning: bool | None = None
    reasoning_effort: str | None = None


@dataclass(frozen=True)
class JudgeConfig:
    name: str
    prompt_version: str
    reference_date: str
    model: JudgeModelConfig
    limits: LimitsConfig
    source_path: Path | None = None

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "prompt_version": self.prompt_version,
            "reference_date": self.reference_date,
            "model": asdict(self.model),
            "limits": asdict(self.limits),
        }

    def request_params(self) -> dict:
        """Todo lo que afecta la respuesta del modelo (entra en la clave de caché)."""
        return asdict(self.model) | {
            "response_format": "json_schema",
            "strict": True,
            "schema_name": JSON_SCHEMA_NAME,
        }

    def config_hash(self) -> str:
        return sha256_json(self.to_dict())


def load_judge_config(path: str | Path) -> JudgeConfig:
    path = Path(path).resolve()
    with path.open("rb") as fh:
        raw = tomllib.load(fh)
    j = raw["judge"]
    cfg = JudgeConfig(
        name=j["name"],
        prompt_version=j["prompt_version"],
        reference_date=j["reference_date"],
        model=JudgeModelConfig(**raw["model"]),
        limits=LimitsConfig(**raw["limits"]),
        source_path=path,
    )
    validate_judge_config(cfg)
    return cfg


def validate_judge_config(cfg: JudgeConfig) -> None:
    m, lim = cfg.model, cfg.limits
    if m.provider not in JUDGE_PROVIDERS:
        raise ValueError(f"provider inválido: {m.provider!r}")
    if not m.model.strip():
        raise ValueError("model no puede estar vacío")
    if cfg.prompt_version != JUDGE_PROMPT_VERSION:
        raise ValueError(f"prompt_version {cfg.prompt_version} != código {JUDGE_PROMPT_VERSION}")
    if not 0.0 <= m.temperature <= 0.5:
        raise ValueError("temperature debe estar en [0, 0.5]")
    if not 128 <= m.max_completion_tokens <= 8192:
        raise ValueError("max_completion_tokens fuera de [128, 8192]")
    if not 0 <= lim.max_retries <= 2:
        raise ValueError("max_retries fuera de [0, 2] (sin reintentos indefinidos)")
    if lim.max_concurrency != 1:
        raise ValueError("el juez corre secuencialmente (max_concurrency = 1)")
    if lim.max_calls < 1 or lim.max_total_tokens < 1:
        raise ValueError("el presupuesto de llamadas y tokens debe ser positivo")
    if not 1 <= lim.timeout_s <= 300:
        raise ValueError("timeout_s fuera de [1, 300]")
    if lim.min_interval_s < 0 or lim.backoff_base_s < 0 or lim.max_retry_after_s < 0:
        raise ValueError("intervalos negativos")
    if lim.max_consecutive_failures < 1:
        raise ValueError("max_consecutive_failures debe ser >= 1")
    date.fromisoformat(cfg.reference_date)
