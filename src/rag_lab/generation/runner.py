"""Fase 1 de la Etapa 2: generación. Lee SOLO resultados de retrieval, chunks y corpus.

Entrada: runs/<split>/<retrieval_run>/ (manifest.json + retrieval_results.jsonl).
Salida:  runs/<split>/<retrieval_run>/gen/<gen_name>/ (generations.jsonl + gen_manifest.json).
No recibe la ruta de labels.jsonl ni importa rag_lab.evaluation.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

from rag_lab.config import PROJECT_ROOT, relative_to_root, resolve_path
from rag_lab.corpus import load_corpus
from rag_lab.generation.calls import Budget, Pacer, ResponseCache, cache_key
from rag_lab.generation.config import GenerationConfig
from rag_lab.generation.context import ChunkStore
from rag_lab.generation.credentials import redact
from rag_lab.generation.gate import gate_score, load_gate
from rag_lab.generation.prompt import _TEMPLATE, ANSWER_SCHEMA, PROMPT_VERSION, build_messages
from rag_lab.generation.providers import (
    AbortRun,
    Generator,
    ProviderError,
    call_with_retries,
)
from rag_lab.generation.response import parse_answer
from rag_lab.generation.temporal import classify_temporal_scope
from rag_lab.hashing import sha256_bytes, sha256_file, sha256_json

DEFAULT_INDEX_ROOT = PROJECT_ROOT / "artifacts" / "index"
REPORTS_DIR = PROJECT_ROOT / "reports"


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def gate_path_for(run_name: str) -> Path:
    return REPORTS_DIR / f"gate_{run_name}.json"


class _Runner:
    def __init__(
        self,
        cfg: GenerationConfig,
        generator: Generator,
        cache: ResponseCache | None,
        budget: Budget,
        pacer: Pacer,
        sleep: Callable[[float], None],
        secret: str | None,
    ):
        self.cfg = cfg
        self.generator = generator
        self.cache = cache
        self.budget = budget
        self.pacer = pacer
        self.sleep = sleep
        self.secret = secret
        self.abort_reason: str | None = None
        self.consecutive_failures = 0
        self._lock = threading.Lock()

    def _fail(self, reason: str) -> None:
        with self._lock:
            if self.abort_reason is None:
                self.abort_reason = reason

    def call(self, messages: list[dict]) -> dict:
        params = self.cfg.request_params()
        key = cache_key(params, messages, ANSWER_SCHEMA)
        if self.cache is not None:
            hit = self.cache.get(key)
            if hit is not None:
                return {"status": "ok", "result": hit, "cache_key": key}
        self.budget.reserve()  # BudgetExceeded (AbortRun) si no hay presupuesto

        def once():
            self.pacer.wait_turn()
            return self.generator.generate(messages, ANSWER_SCHEMA)

        try:
            result = call_with_retries(once, self.cfg.limits, sleep=self.sleep)
        except ProviderError as exc:
            with self._lock:
                self.consecutive_failures += 1
                too_many = self.consecutive_failures >= self.cfg.limits.max_consecutive_failures
            if too_many:
                self._fail(f"{self.consecutive_failures} fallos consecutivos de API")
            err = exc.to_dict()
            err["message"] = redact(err["message"], self.secret)
            return {
                "status": "api_error",
                "error": err,
                "attempts": getattr(exc, "attempts", 1),
                "error_history": getattr(exc, "history", []),
                "cache_key": key,
            }
        with self._lock:
            self.consecutive_failures = 0
        self.budget.add_tokens(int(result.usage.get("total_tokens") or 0))
        self.pacer.observe(result)
        if self.cache is not None:
            self.cache.put(key, result)
        return {"status": "ok", "result": result, "cache_key": key}


def _not_run(row: dict, reason: str) -> dict:
    return {"qid": row["qid"], "question": row["question"], "status": "not_run", "reason": reason}


def run_generation(
    retrieval_run_dir: Path,
    cfg: GenerationConfig,
    generator: Generator,
    out_dir: Path | None = None,
    cache: ResponseCache | None = None,
    qids: list[str] | None = None,
    index_root: Path = DEFAULT_INDEX_ROOT,
    gate_path: Path | None = None,
    sleep: Callable[[float], None] | None = None,
    secret: str | None = None,
) -> Path:
    import time

    if cfg.prompt_version != PROMPT_VERSION:
        raise ValueError(f"prompt_version {cfg.prompt_version} != código {PROMPT_VERSION}")
    if generator.provider != cfg.model.provider:
        raise ValueError("el generador no coincide con el provider de la configuración")
    sleep = sleep or time.sleep
    manifest = json.loads((retrieval_run_dir / "manifest.json").read_text(encoding="utf-8"))
    method = manifest["config"]["retrieval"]["method"]
    rows = _read_jsonl(retrieval_run_dir / "retrieval_results.jsonl")
    if qids is not None:
        unknown = set(qids) - {r["qid"] for r in rows}
        if unknown:
            raise ValueError(f"qids inexistentes: {sorted(unknown)}")
        rows = [r for r in rows if r["qid"] in set(qids)]

    index_dir = index_root / manifest["index_id"]
    index_manifest = json.loads((index_dir / "index_manifest.json").read_text(encoding="utf-8"))
    if index_manifest["index_id"] != manifest["index_id"]:
        raise ValueError("el índice en disco no coincide con el de la corrida de retrieval")
    docs = load_corpus(resolve_path(manifest["config"]["corpus_dir"]))
    store = ChunkStore.from_index_dir(index_dir, docs)

    gate = None
    if cfg.gate_enabled:
        gate = load_gate(gate_path or gate_path_for(manifest["run_name"]), manifest)

    runner = _Runner(
        cfg,
        generator,
        cache,
        Budget(cfg.limits.max_calls, cfg.limits.max_total_tokens),
        Pacer(cfg.limits.min_interval_s, sleep=sleep),
        sleep,
        secret,
    )

    def process(row: dict) -> dict:
        if runner.abort_reason:
            return _not_run(row, runner.abort_reason)
        question = row["question"]
        scope = classify_temporal_scope(question, cfg.reference_date)
        context = store.build([r["chunk_id"] for r in row["results"]])
        score = gate_score(row["results"], method)
        out = {
            "qid": row["qid"],
            "question": question,
            "temporal_scope": {"kind": scope.kind, "evidence": scope.evidence},
            "context": [c.to_dict() for c in context],
            "gate": None,
        }
        if gate is not None:
            passed = score is not None and score >= gate["threshold"]
            out["gate"] = {
                "score": score,
                "threshold": gate["threshold"],
                "score_type": gate["score_type"],
                "passed": passed,
            }
            if not passed:
                out.update(
                    status="ok",
                    abstained=True,
                    abstain_cause="gate",
                    answer=None,
                    cited_chunk_ids=[],
                    llm=None,
                )
                return out
        messages = build_messages(question, context, scope, cfg.reference_date)
        out["prompt_sha256"] = sha256_json(messages)
        try:
            res = runner.call(messages)
        except AbortRun as exc:
            runner._fail(str(exc))
            return _not_run(row, runner.abort_reason or str(exc))
        if res["status"] != "ok":
            out.update(
                status="api_error",
                abstained=None,
                abstain_cause=None,
                answer=None,
                cited_chunk_ids=[],
                llm={
                    "error": res["error"],
                    "attempts": res["attempts"],
                    "error_history": res["error_history"],
                },
            )
            return out
        r = res["result"]
        parsed = parse_answer(r.content, [c.cite_id for c in context])
        by_cite = {c.cite_id: c.chunk_id for c in context}
        llm = {
            "cached": r.cached,
            "cache_key": res["cache_key"],
            "attempts": r.attempts,
            "transient_errors": r.errors,
            "latency_s": r.latency_s,
            "usage": r.usage,
            "model_returned": r.model_returned,
            "finish_reason": r.finish_reason,
            "request_id": r.request_id,
            "raw_content": r.content,
            "parsed": parsed.to_dict(),
        }
        if not parsed.format_ok:
            out.update(
                status="format_error",
                abstained=None,
                abstain_cause=None,
                answer=None,
                cited_chunk_ids=[],
                llm=llm,
            )
            return out
        out.update(
            status="ok",
            abstained=parsed.abstain,
            abstain_cause="llm" if parsed.abstain else None,
            answer=parsed.answer,
            cited_chunk_ids=[by_cite[c] for c in parsed.valid_citations],
            llm=llm,
        )
        return out

    with ThreadPoolExecutor(max_workers=cfg.limits.max_concurrency) as pool:
        results = list(pool.map(process, rows))

    out_dir = out_dir or retrieval_run_dir / "gen" / cfg.name
    out_dir.mkdir(parents=True, exist_ok=True)
    with (out_dir / "generations.jsonl").open("w", encoding="utf-8", newline="\n") as fh:
        for r in results:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")

    llm_rows = [r.get("llm") for r in results if r.get("llm")]
    real = [x for x in llm_rows if "cached" in x and not x["cached"]]
    usage_keys = ("prompt_tokens", "completion_tokens", "reasoning_tokens", "total_tokens")
    tokens_real = {k: sum(int(x["usage"].get(k) or 0) for x in real) for k in usage_keys}
    attempts_real = sum(x.get("attempts", 0) for x in llm_rows if not x.get("cached"))
    status_counts: dict[str, int] = {}
    for r in results:
        status_counts[r["status"]] = status_counts.get(r["status"], 0) + 1

    from rag_lab.manifest import environment

    gen_manifest = {
        "stage": 2,
        "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "run_status": "aborted" if runner.abort_reason else "complete",
        "abort_reason": runner.abort_reason,
        "partial_qids": qids,
        "split": manifest["split"],
        "retrieval_run": relative_to_root(retrieval_run_dir),
        "retrieval_run_name": manifest["run_name"],
        "retrieval_method": method,
        "retrieval_config_hash": manifest["config_hash"],
        "index_id": manifest["index_id"],
        "questions_sha256": manifest["questions_sha256"],
        "retrieval_results_sha256": sha256_file(retrieval_run_dir / "retrieval_results.jsonl"),
        "generation_config_path": relative_to_root(cfg.source_path) if cfg.source_path else None,
        "generation_config": cfg.to_dict(),
        "generation_config_hash": cfg.config_hash(),
        "prompt_version": PROMPT_VERSION,
        "prompt_template_sha256": sha256_bytes(_TEMPLATE.encode("utf-8")),
        "answer_schema_sha256": sha256_json(ANSWER_SCHEMA),
        "gate": None
        if gate is None
        else {k: gate[k] for k in ("threshold", "score_type", "rule", "calibration_sha256")},
        "counts": {
            "n_questions": len(results),
            "status": status_counts,
            "gate_abstentions": sum(1 for r in results if r.get("abstain_cause") == "gate"),
            "llm_requests_real": len(real),
            "http_attempts_real": attempts_real,
            "cache_hits": sum(1 for x in llm_rows if x.get("cached")),
            "budget_calls_reserved": runner.budget.calls,
        },
        "tokens_real": tokens_real,
        "latency_s_real_total": round(sum(x["latency_s"] for x in real), 3),
        "environment": environment() | {"groq_sdk": _groq_version()},
    }
    (out_dir / "gen_manifest.json").write_text(
        json.dumps(gen_manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return out_dir


def _groq_version() -> str | None:
    from importlib import metadata

    try:
        return metadata.version("groq")
    except metadata.PackageNotFoundError:
        return None
