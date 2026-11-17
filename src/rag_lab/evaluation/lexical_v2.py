"""Normalización léxica v2 y rescoring de hechos (Etapa 3A). Ver docs/lexical_v2.md.

La v2 se diseñó DESPUÉS de observar los falsos negativos e29 ("25 %") y e31 (guion U+2011 y
espacio fino U+202F) del benchmark de la Etapa 2. Es una corrección de la medición, no del
sistema evaluado. La v1 (`gen_metrics.normalize_text` / `fact_present`) no se modifica y sus
métricas siguen siendo las reportadas; la v2 se publica en columnas separadas.

Pasos de la v2, en orden, ANTES de la normalización v1 (acentos, minúsculas, números
escritos -> dígitos, espacios colapsados):
  1. Unicode NFKC.
  2. Guiones tipográficos (U+2010-2015, U+2212, U+FE58, U+FE63, U+FF0D) -> "-".
  3. Espacios especiales (U+00A0, U+2007, U+2009, U+200A, U+202F, U+205F, U+3000) -> " ".
     Caracteres de ancho cero (U+200B-200D, U+2060, U+FEFF) se eliminan.
  4. Comillas tipográficas y angulares -> comillas simples ASCII.
  5. "N %" -> "N%" (espacio entre número y signo de porcentaje).
No incluye sinónimos, morfología ni paráfrasis: "tiene" y "tienen" siguen siendo distintos.
"""

from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path
from statistics import mean

from rag_lab.config import resolve_path
from rag_lab.corpus import load_corpus
from rag_lab.evaluation.gen_metrics import fact_present, normalize_text
from rag_lab.evaluation.labels import load_labels
from rag_lab.hashing import sha256_file
from rag_lab.runner import _read_jsonl, split_paths

LEXICAL_VERSION = "v2"
DESIGN_NOTE = (
    "La normalización v2 se diseñó después de observar los falsos negativos e29 y e31 del "
    "benchmark de la Etapa 2 (eval). Corrige la medición, no el sistema. La v1 sigue siendo "
    "la métrica oficial de la Etapa 2; v1 y v2 se reportan por separado."
)

DASHES = "‐‑‒–—―−﹘﹣－"
SPACES = "      　"
ZERO_WIDTH = "​‌‍⁠﻿"
QUOTES = {
    "‘": "'",
    "’": "'",
    "‚": "'",
    "‛": "'",
    "“": '"',
    "”": '"',
    "„": '"',
    "«": '"',
    "»": '"',
}
_TABLE = str.maketrans(
    {**dict.fromkeys(DASHES, "-"), **dict.fromkeys(SPACES, " "), **QUOTES}
    | dict.fromkeys(ZERO_WIDTH, None)
)
_PCT = re.compile(r"(\d) +%")


def unicode_clean(text: str) -> str:
    """Pasos 1-5 de la v2 (sin la parte v1)."""
    t = unicodedata.normalize("NFKC", text).translate(_TABLE)
    return _PCT.sub(r"\1%", t)


def normalize_text_v2(text: str) -> str:
    return normalize_text(unicode_clean(text))


def fact_present_v2(fact: str, answer: str) -> bool:
    """Mismo criterio de límites que la v1 (`gen_metrics.fact_present`) sobre texto v2."""
    f = normalize_text_v2(fact)
    if not f:
        return False
    pattern = rf"(?<![\w]){re.escape(f)}(?![\w]|[.,]\d)"
    return re.search(pattern, normalize_text_v2(answer)) is not None


def _mean(vals: list) -> dict:
    vals = [v for v in vals if v is not None]
    return {"value": round(mean(vals), 4) if vals else None, "n": len(vals)}


def rescore_lexical(gen_dir: Path) -> dict:
    """Recalcula las métricas de hechos con v1 y v2 sobre las respuestas guardadas.

    Solo lee artefactos; no escribe en `gen_dir`. Verifica que la v1 recalculada coincide con
    `gen_per_question.jsonl` y `gen_summary.json` guardados.
    """
    gm = json.loads((gen_dir / "gen_manifest.json").read_text(encoding="utf-8"))
    rm = json.loads((resolve_path(gm["retrieval_run"]) / "manifest.json").read_text("utf-8"))
    _, labels_path = split_paths(gm["split"])
    docs = load_corpus(resolve_path(rm["config"]["corpus_dir"]))
    labels = load_labels(labels_path, docs)
    gens = {g["qid"]: g for g in _read_jsonl(gen_dir / "generations.jsonl")}
    saved_rows = _read_jsonl(gen_dir / "gen_per_question.jsonl")
    saved_summary = json.loads((gen_dir / "gen_summary.json").read_text(encoding="utf-8"))

    per_q = []
    v1_mismatch = []
    for row in saved_rows:
        if row["status"] != "ok" or row.get("abstained") or not row["answerable"]:
            continue
        lab = labels[row["qid"]]
        answer = gens[row["qid"]]["answer"] or ""
        h1 = [fact_present(f, answer) for f in lab.required_facts]
        h2 = [fact_present_v2(f, answer) for f in lab.required_facts]
        item = {
            "qid": row["qid"],
            "required_facts_coverage_v1": round(mean(h1), 6) if h1 else None,
            "required_facts_coverage_v2": round(mean(h2), 6) if h2 else None,
            "all_required_facts_v1": int(all(h1)) if h1 else None,
            "all_required_facts_v2": int(all(h2)) if h2 else None,
            "missing_facts_v1": [f for f, h in zip(lab.required_facts, h1, strict=True) if not h],
            "missing_facts_v2": [f for f, h in zip(lab.required_facts, h2, strict=True) if not h],
        }
        if lab.forbidden_facts:
            item["forbidden_present_v1"] = int(
                any(fact_present(f, answer) for f in lab.forbidden_facts)
            )
            item["forbidden_present_v2"] = int(
                any(fact_present_v2(f, answer) for f in lab.forbidden_facts)
            )
        if (
            item["required_facts_coverage_v1"] != row.get("required_facts_coverage")
            or item["missing_facts_v1"] != row.get("missing_facts", [])
            or item.get("forbidden_present_v1") != row.get("forbidden_present")
        ):
            v1_mismatch.append(row["qid"])
        item["changed"] = any(
            item.get(f"{k}_v1") != item.get(f"{k}_v2")
            for k in ("required_facts_coverage", "all_required_facts", "forbidden_present")
        )
        per_q.append(item)

    metrics = {}
    for key in ("required_facts_coverage", "all_required_facts", "forbidden_present"):
        metrics[key] = {
            "v1": _mean([q.get(f"{key}_v1") for q in per_q]),
            "v2": _mean([q.get(f"{key}_v2") for q in per_q]),
        }
    saved = saved_summary["metrics"]["answered_answerable"]
    v1_matches_summary = all(metrics[k]["v1"] == saved[k] for k in metrics)
    return {
        "lexical_version": LEXICAL_VERSION,
        "design_note": DESIGN_NOTE,
        "retrieval_run_name": gm["retrieval_run_name"],
        "generation": gm["generation_config"]["name"],
        "split": gm["split"],
        "generations_sha256": sha256_file(gen_dir / "generations.jsonl"),
        "labels_sha256": sha256_file(labels_path),
        "scope": "respondibles respondidas (mismo denominador que gen_summary.json)",
        "v1_reproduces_saved": not v1_mismatch and v1_matches_summary,
        "v1_mismatch_qids": v1_mismatch,
        "metrics": metrics,
        "changed_qids": [q["qid"] for q in per_q if q["changed"]],
        "per_question": per_q,
    }
