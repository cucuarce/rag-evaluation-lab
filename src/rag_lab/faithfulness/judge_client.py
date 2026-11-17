"""Cliente Groq del juez: el mismo adaptador de la Etapa 2 (mapeo de errores, sin reintentos
propios del SDK, encabezados de rate limit, uso de tokens), con la solicitud del juez:
structured outputs `json_schema` con `strict: true` y el esquema `JUDGE_SCHEMA`.

No hay degradación silenciosa: si el modelo rechaza el modo estricto, el error (400) se
registra como fallo técnico y la corrida no cambia de modo ni de modelo.
"""

from __future__ import annotations

from rag_lab.faithfulness.judge_config import JSON_SCHEMA_NAME, JudgeConfig
from rag_lab.generation.providers import GroqGenerator


class JudgeGroqClient(GroqGenerator):
    provider = "groq"

    def __init__(self, cfg: JudgeConfig, api_key: str, http_client=None):
        # GroqGenerator solo usa cfg.model.model y cfg.limits.timeout_s en su constructor.
        super().__init__(cfg, api_key, http_client=http_client)  # type: ignore[arg-type]

    def _request_kwargs(self, messages: list[dict], schema: dict) -> dict:
        m = self.cfg.model
        kwargs = {
            "model": m.model,
            "messages": messages,
            "temperature": m.temperature,
            "max_completion_tokens": m.max_completion_tokens,
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": JSON_SCHEMA_NAME, "strict": True, "schema": schema},
            },
        }
        if m.seed is not None:
            kwargs["seed"] = m.seed
        if m.include_reasoning is not None:
            kwargs["include_reasoning"] = m.include_reasoning
        if m.reasoning_effort is not None:
            kwargs["reasoning_effort"] = m.reasoning_effort
        return kwargs
