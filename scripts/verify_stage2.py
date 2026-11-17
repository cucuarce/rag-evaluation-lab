"""Verificación de solo lectura de las corridas de la Etapa 2 (no llama a ninguna API).

Comprueba, a partir de los artefactos versionados:
  1. Entradas sin cambios: preguntas, resultados de retrieval, config de generación, prompt,
     esquema y umbral del gate coinciden con lo registrado en cada gen_manifest.json.
  2. Comparabilidad A/B (mismas comprobaciones que `rag-lab compare-gen`).
  3. Re-scoring en memoria desde generations.jsonl con el código de métricas original:
     debe dar exactamente gen_per_question.jsonl y gen_summary.json guardados.
  4. Ausencia de fuga: cada prompt se reconstruye offline, su sha256 debe coincidir con el
     registrado y no debe contener respuestas de referencia, notas ni nombres de campos de
     labels (se excluyen respuestas de referencia que son texto literal del corpus).
  5. Esquema: toda respuesta del modelo valida contra el esquema estricto.
  6. Secretos: ningún patrón de API key de Groq (ni el valor de GROQ_API_KEY, si está
     configurado) aparece en runs/, reports/ ni docs/.
  7. Presupuesto: llamadas y tokens reales dentro de lo autorizado.

Requiere el índice local (`rag-lab index --config configs/a_dense_k5.toml`) para reconstruir
los prompts. Uso: uv run python scripts/verify_stage2.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from rag_lab.config import PROJECT_ROOT as P
from rag_lab.config import resolve_path
from rag_lab.corpus import load_corpus
from rag_lab.evaluation.gen_metrics import aggregate_generation, score_generation_row
from rag_lab.evaluation.gen_scoring import compare_generation
from rag_lab.evaluation.labels import load_labels
from rag_lab.generation.config import load_generation_config
from rag_lab.generation.context import ChunkStore
from rag_lab.generation.credentials import get_api_key
from rag_lab.generation.prompt import _TEMPLATE, ANSWER_SCHEMA, build_messages
from rag_lab.generation.response import parse_answer
from rag_lab.generation.temporal import classify_temporal_scope
from rag_lab.hashing import sha256_bytes, sha256_file, sha256_json
from rag_lab.runner import _read_jsonl, split_paths

GEN = "groq_gpt-oss-120b"
RUNS = {"A": P / "runs/eval/A_dense_k5", "B": P / "runs/eval/B_hybrid_k5"}
SMOKE = [P / "runs/smoke/calibration_A", P / "runs/smoke/eval_A"]
AUTHORIZED = {"calls": 80, "tokens": 110_000}  # benchmark A+B (sin smoke)
LABEL_FIELD_NAMES = ("reference_answer", "required_facts", "forbidden_facts", "gold_evidence")
KEY_PATTERN = re.compile(r"gsk_[A-Za-z0-9]{20,}")

failures: list[str] = []


def check(cond: bool, msg: str) -> bool:
    if not cond:
        failures.append(msg)
    return cond


def verify_run(name: str, run_dir: Path, gen_dir: Path, store: ChunkStore, banned: list[str]):
    gm = json.loads((gen_dir / "gen_manifest.json").read_text("utf-8"))
    rm = json.loads((run_dir / "manifest.json").read_text("utf-8"))
    q_path, labels_path = split_paths(gm["split"])
    out: dict = {"run_status": gm["run_status"]}

    # 1. Entradas sin cambios
    cfg = load_generation_config(resolve_path(gm["generation_config_path"]))
    gate = json.loads((P / f"reports/gate_{gm['retrieval_run_name']}.json").read_text("utf-8"))
    inputs = {
        "questions_sha256": sha256_file(q_path) == gm["questions_sha256"],
        "retrieval_results_sha256": sha256_file(run_dir / "retrieval_results.jsonl")
        == gm["retrieval_results_sha256"],
        "index_id": rm["index_id"] == gm["index_id"],
        "generation_config": cfg.to_dict() == gm["generation_config"],
        "prompt_template_sha256": sha256_bytes(_TEMPLATE.encode("utf-8"))
        == gm["prompt_template_sha256"],
        "answer_schema_sha256": sha256_json(ANSWER_SCHEMA) == gm["answer_schema_sha256"],
        "gate_threshold": gm["gate"] is None
        or (
            gate["threshold"] == gm["gate"]["threshold"]
            and gate["calibration_sha256"] == gm["gate"]["calibration_sha256"]
        ),
    }
    for k, ok in inputs.items():
        check(ok, f"{name}: entrada modificada: {k}")
    out["inputs_unchanged"] = inputs

    # 3. Re-scoring en memoria con el código original
    docs = load_corpus(resolve_path(rm["config"]["corpus_dir"]))
    labels = load_labels(labels_path, docs)
    deprecated = {d.doc_id for d in docs.values() if d.status == "deprecated"}
    tau = rm["config"]["evaluation"]["span_coverage_threshold"]
    gens = _read_jsonl(gen_dir / "generations.jsonl")
    rows = [score_generation_row(g, labels[g["qid"]], tau, deprecated) for g in gens]
    saved_rows = _read_jsonl(gen_dir / "gen_per_question.jsonl")
    saved_summary = json.loads((gen_dir / "gen_summary.json").read_text("utf-8"))
    same_rows = json.loads(json.dumps(rows)) == saved_rows
    same_summary = json.loads(json.dumps(aggregate_generation(rows))) == saved_summary["metrics"]
    check(same_rows and same_summary, f"{name}: el re-scoring no reproduce lo guardado")
    out["rescoring_reproduces_saved"] = same_rows and same_summary

    # 4 y 5. Prompts y esquema
    sent = sha_ok = leaks = schema_ok = 0
    for g in gens:
        if not g.get("llm"):
            continue
        sent += 1
        scope = classify_temporal_scope(g["question"], cfg.reference_date)
        ctx = store.build([c["chunk_id"] for c in g["context"]])
        msgs = build_messages(g["question"], ctx, scope, cfg.reference_date)
        sha_ok += sha256_json(msgs) == g["prompt_sha256"]
        prompt = msgs[0]["content"]
        leaks += any(b in prompt for b in banned) or any(k in prompt for k in LABEL_FIELD_NAMES)
        cite_ids = [c["cite_id"] for c in g["context"]]
        schema_ok += parse_answer(g["llm"]["raw_content"], cite_ids).format_ok
    check(sha_ok == sent, f"{name}: {sent - sha_ok} prompts no se reconstruyen")
    check(leaks == 0, f"{name}: {leaks} prompts con datos de referencia")
    check(schema_ok == sent, f"{name}: {sent - schema_ok} respuestas fuera de esquema")
    out["prompts"] = {
        "sent": sent,
        "sha256_reproduced": sha_ok,
        "with_reference_data": leaks,
        "schema_valid": schema_ok,
    }
    out["counts"] = gm["counts"]
    out["tokens_real"] = gm["tokens_real"]
    out["budget"] = gm["budget"]
    return out, gm


def main() -> int:
    docs = load_corpus(P / "data/corpus")
    corpus_text = "\n".join(d.body for d in docs.values())
    eval_labels = _read_jsonl(split_paths("eval")[1])
    candidates = [lab["reference_answer"] for lab in eval_labels]
    candidates += [lab["notes"] for lab in eval_labels if lab["notes"]]
    banned = [c for c in candidates if c not in corpus_text]
    excluded = sorted({c for c in candidates if c in corpus_text})

    report: dict = {"generation": GEN, "runs": {}}
    manifests = {}
    store_cache: dict[str, ChunkStore] = {}
    for name, run_dir in RUNS.items():
        gen_dir = run_dir / "gen" / GEN
        index_id = json.loads((run_dir / "manifest.json").read_text("utf-8"))["index_id"]
        if index_id not in store_cache:
            store_cache[index_id] = ChunkStore.from_index_dir(
                P / "artifacts/index" / index_id, docs
            )
        report["runs"][name], manifests[name] = verify_run(
            name, run_dir, gen_dir, store_cache[index_id], banned
        )
    report["leakage_excluded_verbatim_in_corpus"] = excluded

    # 2. Comparabilidad
    try:
        compare_generation(RUNS["A"] / "gen" / GEN, RUNS["B"] / "gen" / GEN)
        report["comparable"] = True
    except ValueError as exc:
        report["comparable"] = False
        failures.append(f"no comparables: {exc}")

    # 7. Presupuesto
    calls = sum(m["counts"]["llm_requests_real"] for m in manifests.values())
    tokens = sum(m["tokens_real"]["total_tokens"] for m in manifests.values())
    smoke = [json.loads((d / "gen_manifest.json").read_text("utf-8")) for d in SMOKE]
    report["consumption"] = {
        "benchmark_calls": calls,
        "benchmark_tokens": tokens,
        "authorized": AUTHORIZED,
        "smoke_calls": sum(m["counts"]["llm_requests_real"] for m in smoke),
        "smoke_tokens": sum(m["tokens_real"]["total_tokens"] for m in smoke),
    }
    check(calls <= AUTHORIZED["calls"] and tokens <= AUTHORIZED["tokens"], "presupuesto excedido")

    # 6. Secretos
    key = get_api_key()
    hits = []
    for base in ("runs", "reports", "docs"):
        for f in (P / base).rglob("*"):
            if f.is_file():
                text = f.read_text("utf-8", errors="ignore")
                if KEY_PATTERN.search(text) or (key and key in text):
                    hits.append(f.relative_to(P).as_posix())
    check(not hits, f"posibles secretos en: {hits}")
    report["secret_scan"] = {"files_with_matches": hits, "checked_configured_key": bool(key)}

    report["failures"] = failures
    report["ok"] = not failures
    out = P / "reports/verify_stage2.json"
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"ok": report["ok"], "failures": failures}, ensure_ascii=False))
    print(f"-> {out.relative_to(P).as_posix()}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
