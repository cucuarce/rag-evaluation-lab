"""Adaptador de lectura del dashboard (Etapa 4A). Solo lectura y sin Streamlit.

Lee reportes, corridas y datos ya versionados y los transforma en vistas simples (dicts y
listas) para la interfaz. No escribe archivos, no llama a modelos y no recalcula resultados:
cada número que muestra viene tal cual de un reporte o de una predicción congelada.

Privacidad: las vistas nunca incluyen identificadores de solicitudes del proveedor
(`request_id`), encabezados de rate limit, claves de caché ni mensajes de error crudos (pueden
traer identificadores de la organización). `assert_no_private_data` lo verifica.

Archivos ausentes: un archivo opcional que falta se informa en `issues` y la sección
correspondiente queda vacía; nunca se completa con datos inventados.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from rag_lab.config import PROJECT_ROOT

RUN_A, RUN_B = "A_dense_k5", "B_hybrid_k5"
GENERATION = "groq_gpt-oss-120b"
JUDGE_RUN = "judge-v1-otpm_qwen3.8-27b"
FEATURED_CASES = ("J02", "J12", "J46")
FIELDS = ("label_cited", "label_context")
LABEL_ORDER = (
    "supported",
    "partially_supported",
    "unsupported",
    "insufficient_context",
    "judge_unverifiable",
)
RATIONALE_CUT_CHARS = 496  # ver docs/judge.md, "Corte de los razonamientos en 496 caracteres"

PATHS = {
    "retrieval_compare": "reports/compare_eval_A_dense_k5_vs_B_hybrid_k5.json",
    "questions": "data/eval/questions.jsonl",
    "generation_compare": f"reports/compare_gen_{GENERATION}_{RUN_A}_vs_{RUN_B}.json",
    "lexical_a": f"reports/lexical_v2_{GENERATION}_{RUN_A}.json",
    "lexical_b": f"reports/lexical_v2_{GENERATION}_{RUN_B}.json",
    "judge_comparison": f"reports/judge_{JUDGE_RUN}_comparison.json",
    "judge_manifest": f"runs/stage3/judge/{JUDGE_RUN}/judge_manifest.json",
    "judge_predictions": f"runs/stage3/judge/{JUDGE_RUN}/predictions.jsonl",
    "judge_selection": "data/stage3/judge_full_selection.json",
    "answers": "data/stage3/answers.jsonl",
    "claims": "data/stage3/claims_proposed.jsonl",
    "perturbations": "data/stage3/perturbations.jsonl",
    "human_labels": "data/stage3/human_labels_round1.jsonl",
    "perturbation_review": "data/stage3/perturbation_review.jsonl",
}

# Explicaciones de los estudios de caso: resumen de la auditoría offline documentada en
# docs/judge.md (no se derivan de nuevas llamadas ni modifican predicciones).
CASE_NOTES = {
    "J02": (
        "Generalización. La afirmación habla de «un plan superior (por ejemplo, Pro)», pero "
        "el fragmento S3 solo documenta los cambios Starter → Pro y Pro → Pro Plus. La "
        "referencia humana es partially_supported; el juez dio supported con una cita literal "
        "válida, igual con 1536 y con 640 tokens. judge-v1 no tiene una regla explícita de "
        "generalización."
    ),
    "J12": (
        "Respaldo fuera de lo citado. La respuesta cita solo S1; el dato «Pro incluye 10 "
        "usuarios» está en S3 (no citado) y los 18 usuarios vienen de la pregunta. La etiqueta "
        "cruda del juez (partially_supported) coincidía con la humana, pero su única cita es de "
        "S3: una etiqueta de respaldo exige una cita válida de un fragmento citado, así que el "
        "verificador la convirtió en judge_unverifiable. Cuenta como desacuerdo (citation_error)."
    ),
    "J46": (
        "Control sintético de negación (perturbación de e28-c2). El juez etiquetó supported una "
        "afirmación falsa, con dos citas literales válidas (S1 y S3) que juntas la contradicen. "
        "Las etiquetas se emiten antes del razonamiento, y el razonamiento concluye que la "
        "afirmación «es falsa según los documentos»: no fundamenta la etiqueta. Una cita "
        "literal válida no demuestra faithfulness."
    ),
}

_PRIVATE_KEYS = {"request_id", "ratelimit", "cache_key", "raw_content", "technical_error"}
_PRIVATE_PATTERNS = (
    re.compile(r"\borg_[A-Za-z0-9]{6,}"),
    re.compile(r"\bgsk_[A-Za-z0-9]{6,}"),
    re.compile(r"\breq_[A-Za-z0-9]{6,}"),
)


@dataclass
class Store:
    """Archivos leídos (por clave de PATHS) y problemas encontrados al leerlos."""

    root: Path
    files: dict[str, object] = field(default_factory=dict)
    sha256: dict[str, str] = field(default_factory=dict)
    issues: list[str] = field(default_factory=list)

    def get(self, key: str):
        return self.files.get(key)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read(path: Path):
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".jsonl":
        return [json.loads(line) for line in text.splitlines() if line.strip()]
    return json.loads(text)


def load_store(root: Path = PROJECT_ROOT) -> Store:
    """Lee todos los archivos conocidos. Los que faltan o no se pueden leer van a `issues`."""
    store = Store(root=root)
    for key, rel in PATHS.items():
        path = root / rel
        if not path.exists():
            store.issues.append(f"falta {rel}")
            continue
        try:
            store.files[key] = _read(path)
            store.sha256[key] = _sha256(path)
        except (OSError, ValueError) as exc:
            store.issues.append(f"no se pudo leer {rel}: {type(exc).__name__}")
    return store


# --- Integridad ---------------------------------------------------------------------------


def integrity(store: Store) -> list[dict]:
    """Compara hashes actuales con los registrados en los manifiestos y reportes."""
    checks = []
    man = store.get("judge_manifest")
    rep = store.get("judge_comparison")
    sel = store.get("judge_selection")

    def add(name: str, expected: str | None, actual: str | None) -> None:
        ok = expected is not None and actual is not None and expected == actual
        checks.append(
            {
                "check": name,
                "expected": (expected or "—")[:12],
                "actual": (actual or "—")[:12],
                "ok": ok,
            }
        )

    if man:
        add(
            "predicciones = manifiesto",
            man["predictions_sha256"],
            store.sha256.get("judge_predictions"),
        )
        inputs = man.get("inputs", {})
        for key in ("answers", "claims", "perturbations"):
            add(f"{key} = entrada del juez", inputs.get(key), store.sha256.get(key))
        add(
            "selección = entrada del juez",
            inputs.get("selection_sha256"),
            store.sha256.get("judge_selection"),
        )
    if rep:
        add(
            "reporte de comparación = predicciones",
            rep.get("predictions_sha256"),
            store.sha256.get("judge_predictions"),
        )
    if sel and man:
        add(
            "cases_sha256 de la selección",
            man["inputs"].get("cases_sha256"),
            sel.get("cases_sha256"),
        )
    return checks


# --- Retrieval ----------------------------------------------------------------------------

RETRIEVAL_METRICS = (("recall", "Recall@5"), ("complete", "Complete@5"), ("mrr", "MRR"))


def retrieval_view(store: Store) -> dict | None:
    rep = store.get("retrieval_compare")
    if not rep:
        return None
    questions = {q["qid"]: q["question"] for q in store.get("questions") or []}
    a, b = rep["summary_a"]["overall"], rep["summary_b"]["overall"]
    metrics = [
        {
            "metric": label,
            "A (dense)": a[key],
            "B (hybrid)": b[key],
            "delta B − A": round(b[key] - a[key], 4),
            "n": a[f"{key}_n"],
        }
        for key, label in RETRIEVAL_METRICS
    ]
    by_category = []
    for cat, ma in rep["summary_a"]["by_category"].items():
        mb = rep["summary_b"]["by_category"][cat]
        for key, label in RETRIEVAL_METRICS:
            by_category.append(
                {
                    "categoría": cat,
                    "metric": label,
                    "A (dense)": ma[key],
                    "B (hybrid)": mb[key],
                    "n": ma[f"{key}_n"],
                }
            )
    paired = [
        {
            "metric": label,
            "A mejor": rep["paired"][key]["a_better"],
            "B mejor": rep["paired"][key]["b_better"],
            "empates": rep["paired"][key]["ties"],
            "n": rep["paired"][key]["n"],
            "p (test de signo)": rep["paired"][key]["sign_test_p"],
        }
        for key, label in (("recall", "Recall@5"), ("complete", "Complete@5"), ("rr", "MRR"))
    ]
    per_question = [
        {
            "qid": q["qid"],
            "pregunta": questions.get(q["qid"], ""),
            "categoría": q["category"],
            "respondible": q["answerable"],
            "recall A": q.get("a_recall"),
            "recall B": q.get("b_recall"),
            "complete A": q.get("a_complete"),
            "complete B": q.get("b_complete"),
            "RR A": q.get("a_rr"),
            "RR B": q.get("b_rr"),
            "faltan en A": ", ".join(q.get("a_missing") or []),
            "faltan en B": ", ".join(q.get("b_missing") or []),
            "top-5 A": ", ".join(q["a_retrieved"]),
            "top-5 B": ", ".join(q["b_retrieved"]),
        }
        for q in rep["per_question"]
    ]
    return {
        "n_questions": rep["n_questions"],
        "n_answerable": a["n"],
        "k": rep["shared"]["k"],
        "metrics": metrics,
        "by_category": by_category,
        "paired": paired,
        "per_question": per_question,
        "changed_qids": rep["questions_with_metric_change"],
        "caveat": rep["caveat"],
    }


# --- Generación ---------------------------------------------------------------------------


PAIRED_LABELS = {
    "required_facts_coverage": "Cobertura de required_facts (v1)",
    "all_required_facts": "Todos los required_facts (v1)",
    "forbidden_present": "Hechos prohibidos presentes",
    "citation_precision": "Precisión de citas",
    "cited_evidence_recall": "Recall de evidencia citada",
    "abstained": "Abstención",
}


def generation_view(store: Store) -> dict | None:
    rep = store.get("generation_compare")
    if not rep:
        return None
    sa, sb = rep["summary_a"], rep["summary_b"]

    def pair(label: str, va, vb, n_a, n_b) -> dict:
        return {"metric": label, "A (dense)": va, "B (hybrid)": vb, "n A": n_a, "n B": n_b}

    aa, ab = sa["answered_answerable"], sb["answered_answerable"]
    official = [
        pair(
            "Cobertura de required_facts (v1)",
            aa["required_facts_coverage"]["value"],
            ab["required_facts_coverage"]["value"],
            aa["required_facts_coverage"]["n"],
            ab["required_facts_coverage"]["n"],
        ),
        pair(
            "Todos los required_facts (v1)",
            aa["all_required_facts"]["value"],
            ab["all_required_facts"]["value"],
            aa["all_required_facts"]["n"],
            ab["all_required_facts"]["n"],
        ),
        pair(
            "Precisión de citas",
            aa["citation_precision"]["value"],
            ab["citation_precision"]["value"],
            aa["citation_precision"]["n"],
            ab["citation_precision"]["n"],
        ),
        pair(
            "Recall de evidencia citada",
            aa["cited_evidence_recall"]["value"],
            ab["cited_evidence_recall"]["value"],
            aa["cited_evidence_recall"]["n"],
            ab["cited_evidence_recall"]["n"],
        ),
        pair(
            "Validez de citas (todas las respondidas)",
            sa["citations_all_answered"]["citation_validity"]["value"],
            sb["citations_all_answered"]["citation_validity"]["value"],
            sa["citations_all_answered"]["n_answered"],
            sb["citations_all_answered"]["n_answered"],
        ),
    ]
    abst = []
    for label, key, sub in (
        ("Respondibles respondidas", "answerable", "answered"),
        ("Respondibles abstenidas por el gate", "answerable", "abstained_gate"),
        ("Respondibles abstenidas por el LLM", "answerable", "abstained_llm"),
        ("No respondibles abstenidas por el gate", "unanswerable", "abstained_gate"),
        ("No respondibles abstenidas por el LLM", "unanswerable", "abstained_llm"),
        ("No respondibles respondidas (indebidas)", "unanswerable", "improper_answers"),
    ):
        abst.append(pair(label, sa[key][sub], sb[key][sub], sa[key]["n"], sb[key]["n"]))

    lexical = []
    per_q_lex = []
    for run_key, run_label in (("lexical_a", "A (dense)"), ("lexical_b", "B (hybrid)")):
        lex = store.get(run_key)
        if not lex:
            continue
        for metric, label in (
            ("required_facts_coverage", "Cobertura de required_facts"),
            ("all_required_facts", "Todos los required_facts"),
        ):
            m = lex["metrics"][metric]
            lexical.append(
                {
                    "corrida": run_label,
                    "metric": label,
                    "v1 (oficial Etapa 2)": m["v1"]["value"],
                    "v2": m["v2"]["value"],
                    "n": m["v2"]["n"],
                }
            )
        for q in lex["per_question"]:
            if q["changed"]:
                per_q_lex.append(
                    {
                        "corrida": run_label,
                        "qid": q["qid"],
                        "cobertura v1": q["required_facts_coverage_v1"],
                        "cobertura v2": q["required_facts_coverage_v2"],
                        "faltantes v1": ", ".join(q["missing_facts_v1"]),
                        "faltantes v2": ", ".join(q["missing_facts_v2"]),
                    }
                )
    design_note = (store.get("lexical_a") or store.get("lexical_b") or {}).get("design_note")
    return {
        "official": official,
        "abstention": abst,
        "errors": {"A": sa["errors"], "B": sb["errors"]},
        "gates": {
            "A": rep["gate_a"]["threshold"],
            "B": rep["gate_b"]["threshold"],
            "A_score": rep["gate_a"]["score_type"],
            "B_score": rep["gate_b"]["score_type"],
        },
        "lexical": lexical,
        "lexical_changed": per_q_lex,
        "lexical_design_note": design_note,
        "paired": [
            {
                "métrica": PAIRED_LABELS.get(k, k),
                "pares": d.get("n_pairs"),
                "A mejor": d.get("a_better"),
                "B mejor": d.get("b_better"),
                "empates": d.get("ties"),
                "p (test de signo)": d.get("sign_test_p"),
                "difieren en": ", ".join(d.get("differs_in") or []),
            }
            for k, d in rep["paired"].items()
        ],
        "note": rep["note"],
    }


# --- Faithfulness -------------------------------------------------------------------------


MATRIX_CORNER = "referencia → juez"


def matrix_columns(cms: list[dict]) -> list[str]:
    """Columnas de un grupo: toda clase con algún caso (como fila o como columna) en
    cualquiera de sus matrices, y siempre judge_unverifiable. Solo se omiten clases sin casos."""
    keep = {"judge_unverifiable"}
    for cm in cms:
        for ref, row in cm["counts"].items():
            if any(row.values()):
                keep.add(ref)
            keep.update(c for c, v in row.items() if v)
    return [c for c in LABEL_ORDER if c in keep]


def _matrix_rows(cm: dict, cols: list[str]) -> list[dict]:
    """Filas con casos; la columna total es la suma de la fila (denominador por clase)."""
    rows = []
    for ref in cm["rows_reference"]:
        counts = cm["counts"][ref]
        if not any(counts.values()):
            continue
        row = {MATRIX_CORNER: ref} | {c: counts.get(c, 0) for c in cols}
        row["total"] = sum(counts.values())
        rows.append(row)
    return rows


def _kappa_reading(cmp: dict) -> str | None:
    """Interpretación de la kappa ya calculada (no la recalcula): con una sola clase en la
    referencia o en el juez, la kappa es degenerada y no se debe leer como acuerdo."""
    counts = cmp["confusion_matrix"]["counts"]
    ref_classes = [r for r, row in counts.items() if any(row.values())]
    judge_classes = {c for row in counts.values() for c, v in row.items() if v}
    if len(ref_classes) <= 1:
        return "no aplica: la referencia tiene una sola clase"
    if len(judge_classes) <= 1:
        return "no informativa: el juez usó una sola clase"
    return None


def _field_summary(cmp: dict, cols: list[str]) -> dict:
    ag = cmp["agreement"]
    over = cmp["evaluated_supported_reference_not"]
    return {
        "kappa_lectura": _kappa_reading(cmp),
        "n": cmp["n_compared"],
        "acuerdos": ag["k"],
        "acuerdo": ag["value"],
        "wilson95": ag["wilson95"],
        "kappa": cmp["cohen_kappa"]["value"],
        "kappa_nota": cmp["cohen_kappa"]["note"],
        "supported_indebido": over["claim_ids"],
        "n_referencia_no_supported": over["n_reference_not_supported"],
        "matriz": _matrix_rows(cmp["confusion_matrix"], cols),
        "omitidas": [c for c in cmp["confusion_matrix"]["cols_evaluated"] if c not in cols],
    }


GROUP_LABELS = {
    "originales": "Afirmaciones originales (30, etiqueta humana)",
    "perturbaciones_sinteticas": "Controles sintéticos (17, perturbaciones confirmadas)",
}


def faithfulness_view(store: Store) -> dict | None:
    rep = store.get("judge_comparison")
    man = store.get("judge_manifest")
    if not rep:
        return None
    groups = {}
    for name, d in rep["per_group"].items():
        cols = matrix_columns([d[f]["confusion_matrix"] for f in FIELDS])
        groups[name] = {f: _field_summary(d[f], cols) for f in FIELDS}
    stab = rep.get("pilot_stability") or {}
    run = None
    if man:
        run = {
            "estado": man["run_status"],
            "casos": man["counts"]["n_cases"],
            "solicitudes": man["counts"]["http_requests"],
            "tokens": man["tokens_real"]["total_tokens"],
            "modelo": man["request_params"]["model"],
            "prompt": man["prompt_version"],
            "max_completion_tokens": man["request_params"]["max_completion_tokens"],
            "temperature": man["request_params"]["temperature"],
            "seed": man["request_params"]["seed"],
            "latencia_media_s": man["latency_s"]["mean"],
        }
    rows = [
        {
            "caso": r["case_id"],
            "tipo": "sintético" if r["synthetic_control"] else "original",
            "fuente": r["source_id"],
            "cited humano": r["label_cited"]["reference"],
            "cited juez": r["label_cited"]["judge_final"],
            "cited resultado": r["label_cited"]["outcome"],
            "context humano": r["label_context"]["reference"],
            "context juez": r["label_context"]["judge_final"],
            "context resultado": r["label_context"]["outcome"],
        }
        for r in rep["per_case"]
    ]
    return {
        "n_cases": rep["n_cases"],
        "groups": groups,
        "group_labels": GROUP_LABELS,
        "unverifiable": rep["unverifiable_cases"],
        "invalid_quotes": rep["invalid_quote_cases"],
        "stability": {
            "n": stab.get("n_comparable"),
            "same": stab.get("same"),
            "changed": stab.get("changed"),
        },
        "run": run,
        "per_case": rows,
        "note": rep["note"],
    }


# --- Failure explorer ---------------------------------------------------------------------


def case_ids(store: Store) -> list[str]:
    sel = store.get("judge_selection") or {}
    return [c["case_id"] for c in sel.get("cases", [])]


def case_detail(store: Store, case_id: str) -> dict | None:
    preds = {p["case_id"]: p for p in store.get("judge_predictions") or []}
    rep = {r["case_id"]: r for r in (store.get("judge_comparison") or {}).get("per_case", [])}
    if case_id not in preds or case_id not in rep:
        return None
    p, r = preds[case_id], rep[case_id]
    answers = {a["answer_id"]: a for a in store.get("answers") or []}
    perts = {x["pert_id"]: x for x in store.get("perturbations") or []}
    human = {h["claim_id"]: h for h in store.get("human_labels") or []}
    reviews = {x["pert_id"]: x for x in store.get("perturbation_review") or []}
    answer = answers.get(p["answer_id"], {})
    synthetic = p["type"] == "perturbation"
    pert = perts.get(p["source_id"]) if synthetic else None
    source_claim = pert["source_claim_id"] if pert else p["source_id"]
    h = human.get(source_claim, {})
    judge = p["judge"] or {}
    cited = set(answer.get("cited_cite_ids", []))
    rationale = judge.get("rationale") or ""
    return {
        "case_id": case_id,
        "tipo": "control sintético (perturbación)" if synthetic else "afirmación original",
        "source_id": p["source_id"],
        "qid": p["qid"],
        "pregunta": answer.get("question", ""),
        "respuesta": answer.get("answer", ""),
        "afirmacion_juzgada": p["claim_text"],
        "afirmacion_original": pert["original_text"] if pert else None,
        "cambio": pert["change"] if pert else None,
        "tipo_perturbacion": pert["kind"] if pert else None,
        "revision_humana_perturbacion": (
            reviews.get(p["source_id"], {}).get("human_confirms_expected") if synthetic else None
        ),
        "fragmentos_citados": sorted(cited),
        "contexto": [
            {
                "cite_id": c["cite_id"],
                "citado": c["cite_id"] in cited,
                "documento": c["doc_id"],
                "versión": c["version"],
                "estado": c["status"],
                "texto": c["text"],
            }
            for c in answer.get("context", [])
        ],
        "evidencia_juez": [
            {
                "cite_id": e["cite_id"],
                "fragmento citado": e["cite_id"] in cited,
                "cita literal": e["literal_match"],
                "válida": e["valid"],
                "quote": e["quote"],
            }
            for e in judge.get("evidence_checks", [])
        ],
        "etiquetas": [
            {
                "campo": f,
                "referencia": r[f]["reference"],
                "origen referencia": (
                    "perturbación confirmada (esperado)" if synthetic else "humano, ronda 1"
                ),
                "juez (cruda)": judge.get(f"{f}_raw"),
                "juez (verificada)": judge.get(f),
                "resultado": r[f]["outcome"],
            }
            for f in FIELDS
        ],
        "humano_original": (
            {
                "label_cited": h.get("label_cited"),
                "label_context": h.get("label_context"),
                "support_cite_ids": h.get("support_cite_ids"),
                "nota": h.get("notes") or "",
            }
            if h
            else None
        ),
        "razonamiento": rationale,
        "razonamiento_cortado": len(rationale) == RATIONALE_CUT_CHARS,
        "estado": p["status"],
        "finish_reason": (p["llm"] or {}).get("finish_reason"),
        "nota": CASE_NOTES.get(case_id),
    }


# --- Privacidad ---------------------------------------------------------------------------


def _walk(obj, path: str = ""):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield f"{path}.{k}", k, v
            yield from _walk(v, f"{path}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from _walk(v, f"{path}[{i}]")


def assert_no_private_data(view) -> None:
    """Falla si una vista contiene claves privadas o patrones de identificadores/secretos."""
    for path, key, value in _walk(view):
        if key in _PRIVATE_KEYS:
            raise AssertionError(f"clave privada en la vista: {path}")
        if isinstance(value, str):
            for pat in _PRIVATE_PATTERNS:
                if pat.search(value):
                    raise AssertionError(f"identificador privado en la vista: {path}")
