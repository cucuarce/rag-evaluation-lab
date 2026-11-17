"""Adaptadores de generación (Groq y uno simulado) con reintentos acotados.

Interfaz común (`Generator`): `generate(messages, schema) -> GenerationResult`.
- GroqGenerator: SDK oficial `groq` con max_retries=0 en el cliente; los reintentos los
  controla `call_with_retries` (política explícita y testeable).
- FakeGenerator: determinístico, sin red. Extrae la primera oración del primer fragmento
  utilizable del prompt. Sirve para probar el pipeline, no para medir calidad.

Ollama no está implementado: bastaría otra clase con el mismo método `generate`.

Política de errores:
- transitorios (timeout, conexión, 5xx, 429 con retry-after <= max_retry_after_s):
  hasta `max_retries` reintentos con backoff exponencial (o retry-after si viene).
- 429 con retry-after mayor (o sin reintentos restantes) -> `AbortRun` (cuota): se frena.
- 401/403/404 -> `AbortRun` (credenciales/modelo): se frena.
- 400/422 -> error por pregunta, sin reintento (no se repiten llamadas por defecto).
"""

from __future__ import annotations

import json
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol

from rag_lab.generation.config import GenerationConfig, LimitsConfig

RATELIMIT_HEADERS = (
    "x-ratelimit-limit-requests",
    "x-ratelimit-limit-tokens",
    "x-ratelimit-remaining-requests",
    "x-ratelimit-remaining-tokens",
    "x-ratelimit-reset-requests",
    "x-ratelimit-reset-tokens",
    "retry-after",
)


@dataclass
class GenerationResult:
    content: str | None
    usage: dict
    latency_s: float
    model_returned: str | None = None
    finish_reason: str | None = None
    request_id: str | None = None
    ratelimit: dict = field(default_factory=dict)
    attempts: int = 1
    errors: list[dict] = field(default_factory=list)  # errores transitorios previos
    cached: bool = False

    def to_record(self) -> dict:
        return {
            "content": self.content,
            "usage": self.usage,
            "latency_s": self.latency_s,
            "model_returned": self.model_returned,
            "finish_reason": self.finish_reason,
            "request_id": self.request_id,
        }


class ProviderError(Exception):
    def __init__(
        self,
        kind: str,
        message: str,
        status: int | None = None,
        transient: bool = False,
        retry_after: float | None = None,
    ):
        super().__init__(message)
        self.kind = kind
        self.message = message[:500]
        self.status = status
        self.transient = transient
        self.retry_after = retry_after

    def to_dict(self) -> dict:
        return {
            "kind": self.kind,
            "status": self.status,
            "message": self.message,
            "retry_after": self.retry_after,
        }


class AbortRun(Exception):
    """Condición que obliga a frenar la corrida completa (cuota, credenciales, presupuesto)."""


FATAL_KINDS = {"auth", "permission", "not_found"}


class Generator(Protocol):
    provider: str
    model: str

    def generate(self, messages: list[dict], schema: dict) -> GenerationResult: ...


def call_with_retries(
    fn: Callable[[], GenerationResult],
    limits: LimitsConfig,
    sleep: Callable[[float], None] = time.sleep,
) -> GenerationResult:
    errors: list[dict] = []
    for attempt in range(limits.max_retries + 1):
        try:
            result = fn()
        except ProviderError as exc:
            errors.append(exc.to_dict())
            if exc.kind in FATAL_KINDS:
                raise AbortRun(f"{exc.kind} (HTTP {exc.status}): {exc.message}") from exc
            if exc.kind == "rate_limit":
                if exc.retry_after is not None and exc.retry_after > limits.max_retry_after_s:
                    raise AbortRun(
                        f"rate limit/cuota: retry-after {exc.retry_after:.0f}s supera "
                        f"max_retry_after_s={limits.max_retry_after_s:.0f}s"
                    ) from exc
                if attempt == limits.max_retries:
                    raise AbortRun("rate limit persistente: reintentos agotados") from exc
            if not exc.transient or attempt == limits.max_retries:
                exc.attempts = attempt + 1  # type: ignore[attr-defined]
                exc.history = errors  # type: ignore[attr-defined]
                raise
            wait = (
                exc.retry_after
                if exc.retry_after is not None
                else limits.backoff_base_s * (2**attempt)
            )
            sleep(wait)
            continue
        result.attempts = attempt + 1
        result.errors = errors
        return result
    raise AssertionError("inalcanzable")


def parse_reset(value: str | None) -> float | None:
    """'7.66s' | '2m59.56s' | '350ms' | '1h2m3s' -> segundos."""
    if not value:
        return None
    total = 0.0
    matched = False
    for num, unit in re.findall(r"([\d.]+)(ms|h|m|s)", value):
        matched = True
        total += float(num) * {"ms": 0.001, "s": 1, "m": 60, "h": 3600}[unit]
    if matched:
        return total
    try:
        return float(value)
    except ValueError:
        return None


class GroqGenerator:
    provider = "groq"

    def __init__(self, cfg: GenerationConfig, api_key: str, http_client=None):
        from groq import Groq

        if not api_key:
            raise ValueError("Falta GROQ_API_KEY")
        self.cfg = cfg
        self.model = cfg.model.model
        self._client = Groq(
            api_key=api_key,
            timeout=cfg.limits.timeout_s,
            max_retries=0,  # los reintentos los controla call_with_retries
            http_client=http_client,
        )

    def _request_kwargs(self, messages: list[dict], schema: dict) -> dict:
        m = self.cfg.model
        kwargs = {
            "model": m.model,
            "messages": messages,
            "temperature": m.temperature,
            "max_completion_tokens": m.max_completion_tokens,
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "kestrel_answer", "strict": True, "schema": schema},
            },
            "include_reasoning": False,
        }
        if m.reasoning_effort is not None:
            kwargs["reasoning_effort"] = m.reasoning_effort
        if m.seed is not None:
            kwargs["seed"] = m.seed
        return kwargs

    def _call_once(self, messages: list[dict], schema: dict) -> GenerationResult:
        import groq

        t0 = time.perf_counter()
        try:
            raw = self._client.chat.completions.with_raw_response.create(
                **self._request_kwargs(messages, schema)
            )
            completion = raw.parse()
        except groq.RateLimitError as exc:
            ra = exc.response.headers.get("retry-after")
            raise ProviderError(
                "rate_limit",
                str(exc.message),
                429,
                transient=True,
                retry_after=float(ra) if ra else None,
            ) from exc
        except groq.APITimeoutError as exc:
            raise ProviderError("timeout", "timeout", transient=True) from exc
        except groq.APIConnectionError as exc:
            raise ProviderError("connection", str(exc.message), transient=True) from exc
        except groq.AuthenticationError as exc:
            raise ProviderError("auth", str(exc.message), exc.status_code) from exc
        except groq.PermissionDeniedError as exc:
            raise ProviderError("permission", str(exc.message), exc.status_code) from exc
        except groq.NotFoundError as exc:
            raise ProviderError("not_found", str(exc.message), exc.status_code) from exc
        except groq.APIStatusError as exc:
            status = exc.status_code
            kind = "server_error" if status >= 500 else "bad_request"
            raise ProviderError(kind, str(exc.message), status, transient=status >= 500) from exc
        latency = time.perf_counter() - t0
        usage = completion.usage
        usage_d = {}
        if usage is not None:
            usage_d = {
                "prompt_tokens": usage.prompt_tokens,
                "completion_tokens": usage.completion_tokens,
                "total_tokens": usage.total_tokens,
            }
            details = getattr(usage, "completion_tokens_details", None)
            rt = getattr(details, "reasoning_tokens", None) if details else None
            if rt is not None:
                usage_d["reasoning_tokens"] = rt
        choice = completion.choices[0] if completion.choices else None
        return GenerationResult(
            content=choice.message.content if choice else None,
            usage=usage_d,
            latency_s=round(latency, 3),
            model_returned=completion.model,
            finish_reason=choice.finish_reason if choice else None,
            request_id=raw.headers.get("x-request-id") or completion.id,
            ratelimit={h: raw.headers.get(h) for h in RATELIMIT_HEADERS if raw.headers.get(h)},
        )

    def generate(self, messages: list[dict], schema: dict) -> GenerationResult:
        return self._call_once(messages, schema)


_FRAGMENT = re.compile(r"^\[(S\d+)\] .*?estado: (VIGENTE|HISTÓRICO)[^\n]*\n(.+)$", re.M)


class FakeGenerator:
    """Generador simulado y determinístico (sin red, sin modelo).

    - Sin fragmentos -> abstención (insufficient_evidence).
    - Consulta vigente -> primer fragmento VIGENTE; histórica -> primer fragmento HISTÓRICO.
    - Respuesta = primera oración de ese fragmento, citándolo.
    """

    provider = "fake"

    def __init__(self, model: str = "fake-extractive-v1"):
        self.model = model

    def generate(self, messages: list[dict], schema: dict) -> GenerationResult:
        prompt = messages[-1]["content"]
        frags = _FRAGMENT.findall(prompt)
        historical = "la pregunta es HISTÓRICA" in prompt
        wanted = "HISTÓRICO" if historical else "VIGENTE"
        pick = next((f for f in frags if f[1] == wanted), None)
        if pick is None:
            out = {
                "answer": "La base de conocimiento no tiene esa información.",
                "citations": [],
                "abstain": True,
                "abstain_reason": "insufficient_evidence",
            }
        else:
            first = re.split(r"(?<=[.!?])\s", pick[2].strip(), maxsplit=1)[0]
            out = {
                "answer": first,
                "citations": [pick[0]],
                "abstain": False,
                "abstain_reason": "none",
            }
        content = json.dumps(out, ensure_ascii=False)
        pt, ct = len(prompt) // 4, len(content) // 4
        return GenerationResult(
            content=content,
            usage={"prompt_tokens": pt, "completion_tokens": ct, "total_tokens": pt + ct},
            latency_s=0.0,
            model_returned=self.model,
            finish_reason="stop",
            request_id=None,
        )
