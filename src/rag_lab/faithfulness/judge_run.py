"""Ejecución del juez semántico (Etapa 3B). Produce predicciones; NO compara con humanos.

Independencia: este módulo nunca lee etiquetas humanas, revisiones de perturbaciones,
etiquetas esperadas, métricas ni notas. De cada caso usa solo el texto de la afirmación (la
original o la perturbada) y la respuesta única de `answers.jsonl` (pregunta, alcance temporal,
contexto y citas). El prompt lo arma `build_judge_messages` (judge-v1, sin cambios), con un
identificador neutro (`A1`) para que el juez no vea IDs que revelen perturbaciones.

Una afirmación por solicitud: un caso = como máximo una solicitud HTTP (max_retries = 0 en la
config del smoke). Las predicciones se escriben antes de cualquier comparación y quedan con su
sha256 en el manifiesto.

Clasificación técnica de cada caso (sin referencia humana):
- ok: JSON válido según el esquema y con la afirmación pedida.
- format_error: el contenido no cumple el esquema (incluye truncado por max_completion_tokens).
- incomplete: JSON válido sin la afirmación pedida.
- api_error: la solicitud falló (HTTP 4xx/5xx, timeout, conexión, 429).
- not_run: no se envió (presupuesto, aborto previo o cuota).
Los problemas de cita (judge_unverifiable, citas inválidas) se marcan aparte; el error
semántico solo se define al comparar con la referencia humana (judge_compare).
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from rag_lab.faithfulness.judge_config import JSON_SCHEMA_NAME, JudgeConfig
from rag_lab.faithfulness.judge_prompt import (
    JUDGE_PROMPT_VERSION,
    build_judge_messages,
    template_sha256,
)
from rag_lab.faithfulness.judge_verify import verify_judgment
from rag_lab.faithfulness.schema import JUDGE_SCHEMA, JUDGE_UNVERIFIABLE, write_jsonl
from rag_lab.generation.calls import (
    Budget,
    BudgetExceeded,
    Pacer,
    ResponseCache,
    cache_key,
    estimate_tokens,
)
from rag_lab.generation.credentials import redact as _redact_secret
from rag_lab.generation.providers import AbortRun, ProviderError, call_with_retries
from rag_lab.hashing import sha256_file, sha256_json

REQUEST_CLAIM_ID = "A1"
PROGRESS_FILE = "predictions.progress.jsonl"
# Los mensajes de error de Groq incluyen el identificador de la organización: no se guarda.
ORG_ID_RE = re.compile(r"\borg_[A-Za-z0-9]+")


def redact(text: str, secret: str | None) -> str:
    """Quita la clave y los identificadores de organización de un texto de error."""
    return ORG_ID_RE.sub("org_[REDACTADO]", _redact_secret(text, secret))


CASE_TYPES = ("claim", "perturbation")
USAGE_KEYS = ("prompt_tokens", "completion_tokens", "reasoning_tokens", "total_tokens")


def load_cases(selection: dict, claims: dict[str, dict], perturbations: dict[str, dict]) -> list:
    """De la selección congelada toma solo tipo e id; el texto sale de las afirmaciones o de
    las perturbaciones (campo `perturbed_text`). Ningún otro campo pasa al caso."""
    cases = []
    for item in selection["cases"]:
        kind, sid = item["type"], item["id"]
        if kind == "claim":
            src = claims[sid]
            text = src["text"]
        elif kind == "perturbation":
            src = perturbations[sid]
            text = src["perturbed_text"]
        else:
            raise ValueError(f"tipo de caso inválido: {kind!r}")
        cases.append(
            {
                "case_id": item["case_id"],
                "type": kind,
                "source_id": sid,
                "qid": src["qid"],
                "answer_id": src["answer_id"],
                "claim_text": text,
            }
        )
    ids = [c["case_id"] for c in cases]
    if len(set(ids)) != len(ids):
        raise ValueError("case_id duplicado en la selección")
    return cases


def judge_messages(case: dict, answer: dict, reference_date: str) -> list[dict]:
    if answer["answer_id"] != case["answer_id"]:
        raise ValueError(f"{case['case_id']}: answer_id no coincide")
    return build_judge_messages(answer, [(REQUEST_CLAIM_ID, case["claim_text"])], reference_date)


def plan_run(
    cases: list[dict],
    answers: dict[str, dict],
    cfg: JudgeConfig,
    cache: ResponseCache | None = None,
) -> dict:
    """Dimensionamiento previo (sin red): estimación conservadora por caso. Con caché, los
    casos ya respondidos (misma solicitud exacta) no cuentan para llamadas ni tokens."""
    rows = []
    for c in cases:
        msgs = judge_messages(c, answers[c["answer_id"]], cfg.reference_date)
        key = cache_key(cfg.request_params(), msgs, JUDGE_SCHEMA)
        rows.append(
            {
                "case_id": c["case_id"],
                "prompt_chars": sum(len(m["content"]) for m in msgs),
                "estimate_tokens": estimate_tokens(msgs, cfg.model.max_completion_tokens),
                "cached": cache is not None and cache.get(key) is not None,
            }
        )
    pending = [r for r in rows if not r["cached"]]
    total = sum(r["estimate_tokens"] for r in pending)
    return {
        "n_cases": len(rows),
        "n_cached": len(rows) - len(pending),
        "n_to_request": len(pending),
        "per_case": rows,
        "estimate_total_tokens": total,
        "max_calls": cfg.limits.max_calls,
        "max_total_tokens": cfg.limits.max_total_tokens,
        "fits_calls": len(pending) <= cfg.limits.max_calls,
        "fits_tokens_conservative": total <= cfg.limits.max_total_tokens,
    }


class _Caller:
    """Caché + presupuesto + ritmo + tope duro de solicitudes HTTP."""

    def __init__(self, cfg, client, cache, budget, pacer, sleep, secret):
        self.cfg, self.client, self.cache = cfg, client, cache
        self.budget, self.pacer, self.sleep, self.secret = budget, pacer, sleep, secret
        self.http_requests = 0
        self.consecutive_failures = 0
        self.abort_reason: str | None = None

    def _err(self, exc: ProviderError) -> dict:
        d = exc.to_dict()
        d["message"] = redact(d["message"], self.secret)
        return d

    def call(self, messages: list[dict]) -> dict:
        key = cache_key(self.cfg.request_params(), messages, JUDGE_SCHEMA)
        if self.cache is not None:
            hit = self.cache.get(key)
            if hit is not None:
                return {"status": "ok", "result": hit, "cache_key": key, "http_requests": 0}
        if self.abort_reason:
            return {"status": "not_run", "reason": self.abort_reason, "cache_key": key}
        estimate = estimate_tokens(messages, self.cfg.model.max_completion_tokens)
        sent = 0

        def once():
            nonlocal sent
            self.pacer.wait_turn(estimate)
            if self.http_requests >= self.cfg.limits.max_calls:
                raise BudgetExceeded(f"tope de solicitudes HTTP ({self.cfg.limits.max_calls})")
            self.http_requests += 1
            sent += 1
            return self.client.generate(messages, JUDGE_SCHEMA)

        try:
            self.budget.reserve_with_estimate(estimate)
            result = call_with_retries(once, self.cfg.limits, sleep=self.sleep)
        except AbortRun as exc:
            reason = redact(str(exc), self.secret)
            self.abort_reason = self.abort_reason or reason
            cause = exc.__cause__
            if sent and isinstance(cause, ProviderError):
                return {
                    "status": "api_error",
                    "error": self._err(cause),
                    "abort": reason,
                    "cache_key": key,
                    "http_requests": sent,
                }
            return {"status": "not_run", "reason": reason, "cache_key": key, "http_requests": sent}
        except ProviderError as exc:
            self.consecutive_failures += 1
            if exc.kind == "bad_request":
                # 400/422: solicitud o esquema rechazados. No se insiste ni se cambia de modo.
                self.abort_reason = self.abort_reason or (
                    f"solicitud rechazada (HTTP {exc.status}): posible problema de esquema"
                )
            elif self.consecutive_failures >= self.cfg.limits.max_consecutive_failures:
                self.abort_reason = f"{self.consecutive_failures} fallos consecutivos de API"
            return {
                "status": "api_error",
                "error": self._err(exc),
                "error_history": [
                    dict(e, message=redact(e["message"], self.secret))
                    for e in getattr(exc, "history", [])
                ],
                "cache_key": key,
                "http_requests": sent,
            }
        self.consecutive_failures = 0
        self.budget.add_tokens(int(result.usage.get("total_tokens") or 0))
        self.pacer.observe(result)
        if self.cache is not None:
            self.cache.put(key, result)
        return {"status": "ok", "result": result, "cache_key": key, "http_requests": sent}


def _prediction(case: dict, answer: dict, messages: list[dict], res: dict) -> dict:
    out = {
        "case_id": case["case_id"],
        "type": case["type"],
        "source_id": case["source_id"],
        "qid": case["qid"],
        "answer_id": case["answer_id"],
        "request_claim_id": REQUEST_CLAIM_ID,
        "claim_text": case["claim_text"],
        "prompt_sha256": sha256_json(messages),
        "cache_key": res["cache_key"],
        "status": res["status"],
        "technical_error": None,
        "judge": None,
        "citation_flags": None,
        "llm": None,
    }
    if res["status"] == "not_run":
        out["technical_error"] = {"kind": "not_run", "message": res["reason"]}
        out["llm"] = {"http_requests": res.get("http_requests", 0)}
        return out
    if res["status"] == "api_error":
        out["technical_error"] = res["error"] | {"abort": res.get("abort")}
        out["llm"] = {
            "http_requests": res.get("http_requests", 0),
            "error_history": res.get("error_history", []),
        }
        return out
    r = res["result"]
    out["llm"] = {
        "cached": r.cached,
        "http_requests": res["http_requests"],
        "attempts": r.attempts,
        "latency_s": r.latency_s,
        "usage": r.usage,
        "model_returned": r.model_returned,
        "finish_reason": r.finish_reason,
        "request_id": r.request_id,
        "ratelimit": r.ratelimit,
        "raw_content": r.content,
    }
    texts = {c["cite_id"]: c["text"] for c in answer["context"]}
    v = verify_judgment(r.content or "", [REQUEST_CLAIM_ID], texts, answer["cited_cite_ids"])
    if not v["format_ok"]:
        out["status"] = "format_error"
        detail = v["format_error"]
        if r.finish_reason == "length":
            detail = f"salida truncada (finish_reason=length): {detail}"
        out["technical_error"] = {"kind": "format_error", "message": detail}
        return out
    item = v["claims"][0]
    if item.get("missing"):
        out["status"] = "incomplete"
        out["technical_error"] = {"kind": "incomplete", "message": "; ".join(v["issues"])}
        return out
    out["judge"] = {
        "label_cited_raw": item["judge_label_cited"],
        "label_context_raw": item["judge_label_context"],
        "label_cited": item["label_cited"],
        "label_context": item["label_context"],
        "evidence_checks": item["evidence_checks"],
        "rationale": item["rationale"],
        "issues": v["issues"],
    }
    out["citation_flags"] = {
        "unverifiable_cited": item["label_cited"] == JUDGE_UNVERIFIABLE,
        "unverifiable_context": item["label_context"] == JUDGE_UNVERIFIABLE,
        "n_invalid_quotes": item["n_invalid_quotes"],
        "n_quotes": len(item["evidence_checks"]),
    }
    return out


def run_judge(
    cases: list[dict],
    answers: dict[str, dict],
    cfg: JudgeConfig,
    client,
    out_dir: Path,
    cache: ResponseCache | None = None,
    sleep: Callable[[float], None] | None = None,
    secret: str | None = None,
    force: bool = False,
    inputs: dict | None = None,
) -> Path:
    import time

    if client.provider != cfg.model.provider:
        raise ValueError("el cliente no coincide con el provider de la configuración")
    pred_path = out_dir / "predictions.jsonl"
    if pred_path.exists() and not force:
        raise FileExistsError(
            f"{pred_path} ya existe: las predicciones no se sobrescriben (usá --force)"
        )
    sleep = sleep or time.sleep
    caller = _Caller(
        cfg,
        client,
        cache,
        Budget(cfg.limits.max_calls, cfg.limits.max_total_tokens),
        Pacer(cfg.limits.min_interval_s, sleep=sleep),
        sleep,
        secret,
    )
    preds = []
    out_dir.mkdir(parents=True, exist_ok=True)
    # Registro incremental: cada predicción se agrega y se fuerza a disco apenas existe, para
    # que una interrupción del proceso no pierda lo hecho. Las respuestas exitosas además
    # quedan en la caché, de modo que una reanudación no repite solicitudes.
    progress_path = out_dir / PROGRESS_FILE
    with progress_path.open("w", encoding="utf-8", newline="\n") as progress:
        for case in cases:
            answer = answers[case["answer_id"]]
            messages = judge_messages(case, answer, cfg.reference_date)
            pred = _prediction(case, answer, messages, caller.call(messages))
            preds.append(pred)
            progress.write(json.dumps(pred, ensure_ascii=False) + "\n")
            progress.flush()
            os.fsync(progress.fileno())
            if pred["status"] in ("format_error", "incomplete") and not caller.abort_reason:
                # Con strict=true una salida fuera del esquema es un problema de esquema.
                caller.abort_reason = f"{pred['case_id']}: {pred['status']} (se detiene la corrida)"

    write_jsonl(pred_path, preds)

    real = [p["llm"] for p in preds if p["llm"] and p["llm"].get("cached") is False]
    status: dict[str, int] = {}
    for p in preds:
        status[p["status"]] = status.get(p["status"], 0) + 1
    latencies = [x["latency_s"] for x in real]
    ratelimits = [x["ratelimit"] for x in real if x.get("ratelimit")]
    from rag_lab.generation.runner import _groq_version
    from rag_lab.manifest import environment

    manifest = {
        "stage": "3B",
        "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "run_status": "aborted" if caller.abort_reason else "complete",
        "abort_reason": caller.abort_reason,
        "judge_config": cfg.to_dict(),
        "judge_config_hash": cfg.config_hash(),
        "request_params": cfg.request_params(),
        "json_schema_name": JSON_SCHEMA_NAME,
        "judge_schema_sha256": sha256_json(JUDGE_SCHEMA),
        "prompt_version": JUDGE_PROMPT_VERSION,
        "prompt_template_sha256": template_sha256(),
        "request_claim_id": REQUEST_CLAIM_ID,
        "inputs": inputs or {},
        "counts": {
            "n_cases": len(preds),
            "status": status,
            "http_requests": caller.http_requests,
            "llm_responses_real": len(real),
            "cache_hits": sum(1 for p in preds if p["llm"] and p["llm"].get("cached")),
        },
        "budget": {
            "max_calls": cfg.limits.max_calls,
            "max_total_tokens": cfg.limits.max_total_tokens,
            "calls_reserved": caller.budget.calls,
            "tokens_counted": caller.budget.tokens,
        },
        "tokens_real": {k: sum(int(x["usage"].get(k) or 0) for x in real) for k in USAGE_KEYS},
        "latency_s": {
            "total": round(sum(latencies), 3),
            "mean": round(sum(latencies) / len(latencies), 3) if latencies else None,
            "max": max(latencies) if latencies else None,
        },
        "ratelimit_first": ratelimits[0] if ratelimits else None,
        "ratelimit_last": ratelimits[-1] if ratelimits else None,
        "pacer_wait_s": round(caller.pacer.total_wait_s, 2),
        "predictions_sha256": sha256_file(pred_path),
        "environment": environment() | {"groq_sdk": _groq_version()},
    }
    (out_dir / "judge_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return out_dir
