"""Normalización léxica v2: casos Unicode, límites, monotonía sobre datos reales, v1 intacta."""

from __future__ import annotations

import json

import pytest

from rag_lab.config import PROJECT_ROOT
from rag_lab.evaluation.gen_metrics import fact_present, normalize_text
from rag_lab.evaluation.lexical_v2 import fact_present_v2, normalize_text_v2, rescore_lexical
from rag_lab.runner import _read_jsonl

GEN_DIRS = [
    PROJECT_ROOT / "runs/eval/A_dense_k5/gen/groq_gpt-oss-120b",
    PROJECT_ROOT / "runs/eval/B_hybrid_k5/gen/groq_gpt-oss-120b",
]


@pytest.mark.parametrize(
    ("fact", "answer"),
    [
        ("HMAC-SHA256", "la firma HMAC‑SHA256"),  # guion no separable
        ("HMAC-SHA256", "la firma HMAC–SHA256"),  # guion medio
        ("Kestrel-Signature", "en el encabezado Kestrel‑Signature,"),
        ("25%", "el crédito es del 25 % de la cuota"),  # espacio fino
        ("25%", "el crédito es del 25 % de la cuota"),
        ("25%", "el crédito es del 25 % de la cuota"),  # espacio duro
        ("saldo a favor", "como saldo a favor"),
        ("pago pendiente", "estado “pago pendiente”"),
        ("Retry-After", "encabezado Retry​-After"),  # ancho cero
    ],
)
def test_v2_matches_unicode_variants(fact, answer):
    assert fact_present_v2(fact, answer)


def test_v1_unchanged_still_misses_unicode_variants():
    # La v1 no se tocó: sigue fallando donde falló en la Etapa 2.
    assert not fact_present("25%", "del 25 % de la cuota")
    assert not fact_present("HMAC-SHA256", "HMAC‑SHA256")
    assert normalize_text("25 %") != normalize_text_v2("25 %")


@pytest.mark.parametrize(
    ("fact", "answer"),
    [
        ("5", "15 minutos"),
        ("USD 99", "USD 99,9"),
        ("no tienen SLA contractual", "no tiene SLA contractual"),  # sin paráfrasis
        ("25%", "25 por ciento"),  # sin sinónimos
    ],
)
def test_v2_keeps_boundaries_and_no_paraphrase(fact, answer):
    assert not fact_present_v2(fact, answer)


def test_v2_is_superset_of_v1_on_stage2_answers():
    labels = {r["qid"]: r for r in _read_jsonl(PROJECT_ROOT / "data/eval/labels.jsonl")}
    checked = 0
    for d in GEN_DIRS:
        for g in _read_jsonl(d / "generations.jsonl"):
            if not g.get("answer"):
                continue
            lab = labels[g["qid"]]
            for f in [*lab["required_facts"], *lab["forbidden_facts"]]:
                checked += 1
                if fact_present(f, g["answer"]):
                    assert fact_present_v2(f, g["answer"]), (g["qid"], f)
    assert checked > 50


def test_rescore_reproduces_v1_and_does_not_write_into_run_dir():
    for d in GEN_DIRS:
        before = {p.name: p.stat().st_mtime_ns for p in d.iterdir()}
        rep = rescore_lexical(d)
        assert {p.name: p.stat().st_mtime_ns for p in d.iterdir()} == before
        assert rep["v1_reproduces_saved"]
        saved = json.loads((d / "gen_summary.json").read_text("utf-8"))["metrics"]
        aa = saved["answered_answerable"]
        assert rep["metrics"]["required_facts_coverage"]["v1"] == aa["required_facts_coverage"]
        assert "después de observar los falsos negativos e29 y e31" in rep["design_note"]


def test_rescore_stage2_expected_changes():
    a, b = (rescore_lexical(d) for d in GEN_DIRS)
    assert a["changed_qids"] == ["e29", "e31"]
    assert b["changed_qids"] == ["e31"]
    # Las omisiones y paráfrasis no se "arreglan" con v2.
    for rep in (a, b):
        missing = {q["qid"]: q["missing_facts_v2"] for q in rep["per_question"]}
        assert missing["e04"] == ["Retry-After"]
        assert missing["e27"] == ["no tienen SLA contractual"]


def test_known_limitation_decimal_tail_and_zero_impact_on_stage2():
    """Limitación heredada de la v1 (la v2 usa los mismos límites a propósito): el límite
    izquierdo no excluye la parte decimal de otro número, así que "5" coincide con "2,5".
    Se documenta en docs/lexical_v2.md. En la Etapa 2 no cambió ninguna coincidencia."""
    import re

    assert fact_present("5", "2,5 días") and fact_present_v2("5", "2,5 días")

    def strict(f, a):
        f = normalize_text(f)
        pat = rf"(?<![\w])(?<!\d[.,]){re.escape(f)}(?![\w]|[.,]\d)"
        return re.search(pat, normalize_text(a)) is not None

    labels = {r["qid"]: r for r in _read_jsonl(PROJECT_ROOT / "data/eval/labels.jsonl")}
    n = 0
    for d in GEN_DIRS:
        for g in _read_jsonl(d / "generations.jsonl"):
            if not g.get("answer"):
                continue
            lab = labels[g["qid"]]
            for f in [*lab["required_facts"], *lab["forbidden_facts"]]:
                n += 1
                assert fact_present(f, g["answer"]) == strict(f, g["answer"]), (g["qid"], f)
    assert n == 104
