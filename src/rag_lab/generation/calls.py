"""Caché persistente, presupuesto de llamadas/tokens y ritmo de llamadas.

- Caché: clave = sha256 de (parámetros del modelo + mensajes + esquema). Solo se guardan
  respuestas HTTP exitosas (aunque su contenido luego no valide); los errores no se cachean.
  Un hit no cuenta como llamada ni consume presupuesto.
- Presupuesto: máximo de llamadas reales y de tokens reales por comando. Al agotarse se frena
  la corrida (`BudgetExceeded`) y las preguntas restantes quedan como `not_run`.
- Ritmo: separación mínima entre inicios de llamadas y pausa si los encabezados de rate
  limit indican que no quedan tokens por minuto suficientes para la próxima llamada.
"""

from __future__ import annotations

import json
import math
import os
import threading
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from rag_lab.generation.providers import AbortRun, GenerationResult, parse_reset
from rag_lab.hashing import sha256_json


class BudgetExceeded(AbortRun):
    pass


def cache_key(request_params: dict, messages: list[dict], schema: dict) -> str:
    return sha256_json({"params": request_params, "messages": messages, "schema": schema})


class ResponseCache:
    def __init__(self, root: Path):
        self.root = root

    def _path(self, key: str) -> Path:
        return self.root / key[:2] / f"{key}.json"

    def get(self, key: str) -> GenerationResult | None:
        p = self._path(key)
        if not p.exists():
            return None
        rec = json.loads(p.read_text(encoding="utf-8"))
        return GenerationResult(
            content=rec["content"],
            usage=rec["usage"],
            latency_s=rec["latency_s"],
            model_returned=rec.get("model_returned"),
            finish_reason=rec.get("finish_reason"),
            request_id=rec.get("request_id"),
            attempts=0,
            cached=True,
        )

    def put(self, key: str, result: GenerationResult) -> None:
        p = self._path(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        rec = result.to_record() | {"created_at": datetime.now(UTC).isoformat(timespec="seconds")}
        tmp = p.with_suffix(f".tmp{os.getpid()}-{threading.get_ident()}")
        tmp.write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(tmp, p)


class Budget:
    def __init__(self, max_calls: int, max_tokens: int):
        self.max_calls = max_calls
        self.max_tokens = max_tokens
        self.calls = 0
        self.tokens = 0
        self._lock = threading.Lock()

    def reserve(self) -> None:
        self.reserve_with_estimate(0)

    def reserve_with_estimate(self, estimate: int) -> None:
        """Reserva una llamada solo si la estimación conservadora entra en el presupuesto."""
        with self._lock:
            if self.calls >= self.max_calls:
                raise BudgetExceeded(f"presupuesto de llamadas agotado ({self.max_calls})")
            if self.tokens + estimate > self.max_tokens:
                raise BudgetExceeded(
                    f"presupuesto de tokens insuficiente: usados {self.tokens} + estimación "
                    f"{estimate} > {self.max_tokens}"
                )
            self.calls += 1

    def add_tokens(self, n: int) -> None:
        with self._lock:
            self.tokens += n


def estimate_tokens(messages: list[dict], max_completion_tokens: int) -> int:
    """Estimación conservadora previa al envío: prompt a 2,5 caracteres/token (medido en
    este corpus: ~3,2) + el máximo de salida configurado (incluye razonamiento)."""
    chars = sum(len(m["content"]) for m in messages)
    return math.ceil(chars / 2.5) + max_completion_tokens


class Pacer:
    """Ritmo de llamadas a partir de los encabezados de rate limit de la última respuesta.

    Modelo de cubeta de tokens: disponibles(t) = min(L, R + (t - t_obs) * L / 60), con
    L = x-ratelimit-limit-tokens (TPM) y R = x-ratelimit-remaining-tokens observados en t_obs.
    Antes de cada llamada se espera hasta que disponibles >= estimación * (1 + margen).
    Si quedan menos de `rpd_reserve` requests diarios, se aborta (cuota).
    """

    def __init__(
        self,
        min_interval_s: float,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
        safety_margin: float = 0.15,
        rpd_reserve: int = 5,
    ):
        self.min_interval_s = min_interval_s
        self.clock = clock
        self.sleep = sleep
        self.safety_margin = safety_margin
        self.rpd_reserve = rpd_reserve
        self._next_start = 0.0
        self._tpm: tuple[int, int, float] | None = None  # (limit, remaining, t_obs)
        self._remaining_requests: int | None = None
        self.total_wait_s = 0.0
        self._lock = threading.Lock()

    def _sleep(self, seconds: float) -> None:
        if seconds > 0:
            self.total_wait_s += seconds
            self.sleep(seconds)

    def wait_turn(self, estimate: int = 0) -> None:
        with self._lock:
            if self._remaining_requests is not None and (
                self._remaining_requests < self.rpd_reserve
            ):
                raise AbortRun(
                    f"cuota diaria de requests casi agotada (quedan {self._remaining_requests})"
                )
            now = self.clock()
            if now < self._next_start:
                self._sleep(self._next_start - now)
                now = self.clock()
            if self._tpm is not None and estimate > 0:
                limit, remaining, t_obs = self._tpm
                need = min(limit, math.ceil(estimate * (1 + self.safety_margin)))
                available = min(limit, remaining + (now - t_obs) * limit / 60)
                if available < need:
                    self._sleep((need - available) * 60 / limit + 0.5)
                    now = self.clock()
            self._next_start = now + self.min_interval_s

    def observe(self, result: GenerationResult) -> None:
        rl = result.ratelimit
        with self._lock:
            try:
                if rl.get("x-ratelimit-remaining-requests") is not None:
                    self._remaining_requests = int(float(rl["x-ratelimit-remaining-requests"]))
                limit = rl.get("x-ratelimit-limit-tokens")
                remaining = rl.get("x-ratelimit-remaining-tokens")
                if limit is not None and remaining is not None:
                    self._tpm = (int(float(limit)), int(float(remaining)), self.clock())
                    return
            except ValueError:
                return
            # Sin límite informado: si quedan menos tokens que los usados, esperar al reset.
            reset = parse_reset(rl.get("x-ratelimit-reset-tokens"))
            total = int(result.usage.get("total_tokens") or 0)
            if remaining is not None and reset is not None and int(float(remaining)) < total:
                self._next_start = max(self._next_start, self.clock() + reset + 0.5)
