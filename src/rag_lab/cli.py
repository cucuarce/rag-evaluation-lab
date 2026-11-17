"""CLI rag-lab: retrieval (Etapa 1) y generación (Etapa 2). Ver README."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from rag_lab.config import PROJECT_ROOT, load_config

RUNS_DIR = PROJECT_ROOT / "runs"
REPORTS_DIR = PROJECT_ROOT / "reports"


def _dump(obj: object, path: Path | None = None) -> None:
    text = json.dumps(obj, indent=2, ensure_ascii=False)
    if path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        print(f"-> {path.relative_to(PROJECT_ROOT).as_posix()}")


def cmd_validate(args) -> None:
    from rag_lab.validate import validate_data

    report = validate_data(load_config(args.config))
    print(json.dumps(report, indent=2, ensure_ascii=False))
    print("OK: corpus y datasets válidos")


def cmd_index(args) -> None:
    from rag_lab.embeddings import Embedder
    from rag_lab.index import build_index

    cfg = load_config(args.config)
    manifest = build_index(cfg, Embedder(cfg.embedding), force=args.force)
    print(
        f"índice {manifest['index_id']}: {manifest['n_documents']} documentos, "
        f"{manifest['n_chunks']} chunks, máx {manifest['max_chunk_tokens']} tokens/chunk"
    )


def cmd_eval(args) -> None:
    from rag_lab.embeddings import Embedder
    from rag_lab.index import load_index
    from rag_lab.retrieval import build_retriever
    from rag_lab.runner import run_retrieval, score_run

    cfg = load_config(args.config)
    index = load_index(cfg)
    retriever = build_retriever(index, Embedder(cfg.embedding), cfg.retrieval)
    out_dir = Path(args.out) if args.out else RUNS_DIR / args.split / cfg.name
    run_retrieval(cfg, index, retriever, args.split, out_dir)
    summary = score_run(out_dir)
    o = summary["metrics"]["overall"]
    print(
        f"{cfg.name} [{args.split}] n_respondibles={summary['n_answerable']} "
        f"hit@k={o['hit']} recall@k={o['recall']} complete@k={o['complete']} "
        f"mrr@k={o['mrr']} distractor@k={o['distractor']}"
    )
    shown = out_dir.relative_to(PROJECT_ROOT) if out_dir.is_relative_to(PROJECT_ROOT) else out_dir
    print(f"-> {shown.as_posix()}")


def cmd_compare(args) -> None:
    from rag_lab.compare import compare_runs

    a, b = Path(args.run_a), Path(args.run_b)
    report = compare_runs(a, b)
    print(f"{'métrica':<12}{'A':>8}{'B':>8}{'B-A':>8}  A>B  B>A  empates  p(signo)")
    for m, s in report["paired"].items():
        name = "mrr" if m == "rr" else m
        print(
            f"{name:<12}{s['mean_a']!s:>8}{s['mean_b']!s:>8}{s['delta_b_minus_a']!s:>8}"
            f"  {s['a_better']:>3}  {s['b_better']:>3}  {s['ties']:>7}  {s['sign_test_p']}"
        )
    print(f"top-k idéntico en {report['n_topk_identical']}/{report['n_questions']} preguntas")
    out = (
        Path(args.out)
        if args.out
        else REPORTS_DIR / f"compare_{a.parent.name}_{a.name}_vs_{b.name}.json"
    )
    _dump(report, out)


def cmd_stability(args) -> None:
    from rag_lab.stability import run_stability

    cfg = load_config(args.config)
    report = run_stability(cfg, args.split, args.repeats)
    print(
        json.dumps({k: v for k, v in report.items() if k != "scope"}, indent=2, ensure_ascii=False)
    )
    _dump(report, REPORTS_DIR / f"stability_{args.split}_{cfg.name}.json")


CACHE_DIR = PROJECT_ROOT / "cache" / "llm"


def cmd_calibrate_gate(args) -> None:
    from rag_lab.evaluation.gate_calibration import calibrate_gate
    from rag_lab.generation.runner import gate_path_for

    report = calibrate_gate(Path(args.calibration_run))
    print(
        f"gate {report['retrieval_run_name']} ({report['score_type']}): umbral="
        f"{report['threshold']} separable={report['separable_on_calibration']} "
        f"min_respondible={report['min_answerable']} max_no_respondible="
        f"{report['max_unanswerable']}"
    )
    _dump(report, gate_path_for(report["retrieval_run_name"]))


def _make_generator(cfg, http_client=None):
    from rag_lab.generation.credentials import get_api_key
    from rag_lab.generation.providers import FakeGenerator, GroqGenerator

    if cfg.model.provider == "fake":
        return FakeGenerator(cfg.model.model), None
    key = get_api_key()
    if not key:
        raise ValueError("Falta GROQ_API_KEY (variable de entorno o .env en la raíz del proyecto)")
    return GroqGenerator(cfg, key, http_client=http_client), key


def cmd_gen_check(args) -> None:
    from rag_lab.generation.config import load_generation_config
    from rag_lab.generation.credentials import get_api_key, key_status

    cfg = load_generation_config(args.gen_config)
    report = {
        "config_ok": True,
        "generation": cfg.name,
        "provider": cfg.model.provider,
        "model": cfg.model.model,
        "limits": cfg.to_dict()["limits"],
        "api_key": key_status(),
    }
    if args.online and cfg.model.provider == "groq":
        import groq

        from rag_lab.generation.credentials import redact
        from rag_lab.generation.providers import RATELIMIT_HEADERS

        key = get_api_key()
        if not key:
            raise ValueError("Falta GROQ_API_KEY")
        client = groq.Groq(api_key=key, max_retries=0, timeout=30)
        try:
            raw = client.models.with_raw_response.list()
        except groq.APIError as exc:
            status = getattr(exc, "status_code", None)
            raise ValueError(
                f"gen-check online falló: {type(exc).__name__} (HTTP {status}): "
                f"{redact(str(exc.message), key)}"
            ) from exc
        models = raw.parse()
        ids = sorted(m.id for m in models.data)
        target = next((m for m in models.data if m.id == cfg.model.model), None)
        report["online"] = {
            "model_available": target is not None,
            "model_info": target.model_dump() if target is not None else None,
            "ratelimit_headers_on_models_endpoint": {
                h: raw.headers.get(h) for h in RATELIMIT_HEADERS if raw.headers.get(h)
            },
            "n_models_listed": len(ids),
            "models_listed": ids,
        }
        if cfg.model.model not in ids:
            print(json.dumps(report, indent=2, ensure_ascii=False))
            raise ValueError(f"El modelo {cfg.model.model} no está disponible para esta clave")
    print(json.dumps(report, indent=2, ensure_ascii=False))


def cmd_generate(args) -> None:
    from rag_lab.evaluation.gen_scoring import score_generation
    from rag_lab.generation.calls import ResponseCache
    from rag_lab.generation.config import load_generation_config
    from rag_lab.generation.runner import run_generation

    cfg = load_generation_config(args.gen_config)
    generator, secret = _make_generator(cfg)
    cache = None if args.no_cache or cfg.model.provider == "fake" else ResponseCache(CACHE_DIR)
    qids = [q.strip() for q in args.qids.split(",")] if args.qids else None
    run_dir = Path(args.retrieval_run)
    out = Path(args.out) if args.out else None
    gen_dir = run_generation(
        run_dir, cfg, generator, out_dir=out, cache=cache, qids=qids, secret=secret
    )
    gm = json.loads((gen_dir / "gen_manifest.json").read_text(encoding="utf-8"))
    summary = score_generation(gen_dir)  # fase 2: recién acá se leen etiquetas
    m = summary["metrics"]
    print(
        json.dumps(
            {
                "run_status": gm["run_status"],
                "abort_reason": gm["abort_reason"],
                "counts": gm["counts"],
                "tokens_real": gm["tokens_real"],
                "answerable": m["answerable"],
                "unanswerable": m["unanswerable"],
                "answered_answerable": m["answered_answerable"],
                "version_selection": m["version_selection"],
                "errors": m["errors"],
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    shown = gen_dir.relative_to(PROJECT_ROOT) if gen_dir.is_relative_to(PROJECT_ROOT) else gen_dir
    print(f"-> {shown.as_posix()}")
    if gm["run_status"] != "complete":
        raise ValueError(f"corrida abortada: {gm['abort_reason']}")


def cmd_compare_gen(args) -> None:
    from rag_lab.evaluation.gen_scoring import compare_generation

    a, b = Path(args.gen_a), Path(args.gen_b)
    report = compare_generation(a, b)
    print(f"{'métrica':<26}{'pares':>6}  A>B  B>A  empates  p(signo)")
    for m, s in report["paired"].items():
        print(
            f"{m:<26}{s['n_pairs']:>6}  {s['a_better']!s:>3}  {s['b_better']!s:>3}  "
            f"{s['ties']:>7}  {s['sign_test_p']}"
        )
    out = (
        Path(args.out)
        if args.out
        else REPORTS_DIR
        / f"compare_gen_{report['generation']}_{report['run_a']}_vs_{report['run_b']}.json"
    )
    _dump(report, out)


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")  # consola de Windows (cp1252 por defecto)
    p = argparse.ArgumentParser(
        prog="rag-lab", description="RAG Evaluation Lab (Etapa 1: retrieval, Etapa 2: generación)"
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("validate", help="valida corpus, preguntas y etiquetas")
    s.add_argument("--config", required=True)
    s.set_defaults(func=cmd_validate)

    s = sub.add_parser("index", help="construye el índice (chunks + embeddings + Chroma)")
    s.add_argument("--config", required=True)
    s.add_argument("--force", action="store_true", help="reconstruye aunque exista")
    s.set_defaults(func=cmd_index)

    s = sub.add_parser("eval", help="ejecuta retrieval y calcula métricas")
    s.add_argument("--config", required=True)
    s.add_argument("--split", default="eval", choices=["eval", "calibration"])
    s.add_argument("--out", help="directorio de salida (default runs/<split>/<name>)")
    s.set_defaults(func=cmd_eval)

    s = sub.add_parser("compare", help="comparación pareada de dos corridas")
    s.add_argument("run_a")
    s.add_argument("run_b")
    s.add_argument("--out")
    s.set_defaults(func=cmd_compare)

    s = sub.add_parser("stability", help="verifica estabilidad del ranking en este entorno")
    s.add_argument("--config", required=True)
    s.add_argument("--split", default="eval", choices=["eval", "calibration"])
    s.add_argument("--repeats", type=int, default=2)
    s.set_defaults(func=cmd_stability)

    s = sub.add_parser("calibrate-gate", help="calibra el umbral del gate (solo split calibration)")
    s.add_argument("calibration_run", help="p. ej. runs/calibration/A_dense_k5")
    s.set_defaults(func=cmd_calibrate_gate)

    s = sub.add_parser("gen-check", help="valida config de generación y clave (sin generar)")
    s.add_argument("--gen-config", required=True)
    s.add_argument("--online", action="store_true", help="lista modelos en la API (1 GET)")
    s.set_defaults(func=cmd_gen_check)

    s = sub.add_parser("generate", help="genera respuestas sobre una corrida de retrieval")
    s.add_argument("retrieval_run", help="p. ej. runs/eval/A_dense_k5")
    s.add_argument("--gen-config", required=True)
    s.add_argument("--qids", help="subconjunto separado por comas (smoke)")
    s.add_argument("--out", help="default: <retrieval_run>/gen/<nombre>")
    s.add_argument("--no-cache", action="store_true")
    s.set_defaults(func=cmd_generate)

    s = sub.add_parser("compare-gen", help="comparación pareada de dos generaciones")
    s.add_argument("gen_a")
    s.add_argument("gen_b")
    s.add_argument("--out")
    s.set_defaults(func=cmd_compare_gen)

    args = p.parse_args(argv)
    try:
        args.func(args)
    except (ValueError, FileNotFoundError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
