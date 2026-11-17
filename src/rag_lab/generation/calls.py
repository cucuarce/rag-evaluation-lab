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
        with self._lock:
            if self.calls >= self.max_calls:
                raise BudgetExceeded(f"presupuesto de llamadas agotado ({self.max_calls})")
            if self.tokens >= self.max_tokens:
                raise BudgetExceeded(f"presupuesto de tokens agotado ({self.max_tokens})")
            self.calls += 1

    def add_tokens(self, n: int) -> None:
        with self._lock:
            self.tokens += n


class Pacer:
    def __init__(
        self,
        min_interval_s: float,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.min_interval_s = min_interval_s
        self.clock = clock
        self.sleep = sleep
        self._next_start = 0.0
        self._last_tokens = 0
        self._lock = threading.Lock()

    def wait_turn(self) -> None:
        with self._lock:
            now = self.clock()
            if now < self._next_start:
                self.sleep(self._next_start - now)
                now = self.clock()
            self._next_start = now + self.min_interval_s

    def observe(self, result: GenerationResult) -> None:
        """Si quedan menos tokens/minuto que los de la última llamada, espera al reset."""
        total = int(result.usage.get("total_tokens") or 0)
        rl = result.ratelimit
        with self._lock:
            self._last_tokens = max(self._last_tokens, total)
            remaining = rl.get("x-ratelimit-remaining-tokens")
            reset = parse_reset(rl.get("x-ratelimit-reset-tokens"))
            if remaining is not None and reset is not None:
                try:
                    rem = int(float(remaining))
                except ValueError:
                    return
                if rem < self._last_tokens:
                    self._next_start = max(self._next_start, self.clock() + reset + 0.5)
