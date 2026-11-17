"""CLI mínima: validate | index | eval | compare | stability."""

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


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")  # consola de Windows (cp1252 por defecto)
    p = argparse.ArgumentParser(
        prog="rag-lab", description="RAG Evaluation Lab (Etapa 1: retrieval)"
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

    args = p.parse_args(argv)
    try:
        args.func(args)
    except (ValueError, FileNotFoundError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
