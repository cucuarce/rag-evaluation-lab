"""Tests offline del dashboard (Etapa 4A): carga, valores visibles, privacidad y solo lectura."""

from __future__ import annotations

import ast
import json

import pytest

from rag_lab.config import PROJECT_ROOT
from rag_lab.dashboard import data as D

PKG = PROJECT_ROOT / "src/rag_lab/dashboard"


@pytest.fixture(scope="module")
def store():
    return D.load_store()


def _report(key: str) -> dict:
    return json.loads((PROJECT_ROOT / D.PATHS[key]).read_text(encoding="utf-8"))


# --- Carga e integridad ---------------------------------------------------------------------


def test_all_sources_load_and_hashes_match(store):
    assert store.issues == []
    checks = D.integrity(store)
    assert len(checks) == 7 and all(c["ok"] for c in checks), checks


def test_missing_files_are_reported_not_invented(tmp_path):
    empty = D.load_store(tmp_path)
    assert len(empty.issues) == len(D.PATHS)
    assert D.retrieval_view(empty) is None
    assert D.generation_view(empty) is None
    assert D.faithfulness_view(empty) is None
    assert D.case_ids(empty) == [] and D.case_detail(empty, "J02") is None
    assert D.integrity(empty) == []


def test_unreadable_file_is_an_issue(tmp_path):
    rel = D.PATHS["retrieval_compare"]
    (tmp_path / rel).parent.mkdir(parents=True)
    (tmp_path / rel).write_text("{no es json", encoding="utf-8")
    s = D.load_store(tmp_path)
    assert any("no se pudo leer" in i for i in s.issues)
    assert D.retrieval_view(s) is None


def test_building_every_view_does_not_touch_any_file(store):
    before = {k: (PROJECT_ROOT / p).stat().st_mtime_ns for k, p in D.PATHS.items()}
    fresh = D.load_store()
    D.retrieval_view(fresh)
    D.generation_view(fresh)
    D.faithfulness_view(fresh)
    for cid in D.case_ids(fresh):
        D.case_detail(fresh, cid)
    after = {k: (PROJECT_ROOT / p).stat().st_mtime_ns for k, p in D.PATHS.items()}
    assert before == after
    assert fresh.sha256 == store.sha256


def test_dashboard_never_imports_model_clients():
    banned = {"groq", "httpx", "requests", "openai", "rag_lab.generation", "rag_lab.faithfulness"}
    for f in PKG.glob("*.py"):
        tree = ast.parse(f.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            for n in names:
                assert not any(n == b or n.startswith(b + ".") for b in banned), (f.name, n)


# --- Valores visibles = valores de los reportes ---------------------------------------------


def test_retrieval_view_matches_report(store):
    v = D.retrieval_view(store)
    rep = _report("retrieval_compare")
    by = {m["metric"]: m for m in v["metrics"]}
    for key, label in D.RETRIEVAL_METRICS:
        assert by[label]["A (dense)"] == rep["summary_a"]["overall"][key]
        assert by[label]["B (hybrid)"] == rep["summary_b"]["overall"][key]
        assert by[label]["n"] == 30
    assert (by["Recall@5"]["A (dense)"], by["MRR"]["B (hybrid)"]) == (0.9889, 0.95)
    assert len(v["per_question"]) == 40
    unans = [r for r in v["per_question"] if not r["respondible"]]
    assert len(unans) == 10 and all(r["recall A"] is None for r in unans)


def test_generation_view_separates_v1_and_v2(store):
    v = D.generation_view(store)
    lex = {(r["corrida"], r["metric"]): r for r in v["lexical"]}
    a = lex[("A (dense)", "Todos los required_facts")]
    assert (a["v1 (oficial Etapa 2)"], a["v2"], a["n"]) == (0.8621, 0.931, 29)
    assert {r["qid"] for r in v["lexical_changed"]} == {"e29", "e31"}
    assert "después de observar" in v["lexical_design_note"]
    official = {r["metric"]: r for r in v["official"]}
    assert official["Cobertura de required_facts (v1)"]["A (dense)"] == 0.8793
    abst = {r["metric"]: r for r in v["abstention"]}
    assert abst["No respondibles respondidas (indebidas)"]["A (dense)"] == 0


def test_faithfulness_view_keeps_groups_separate(store):
    v = D.faithfulness_view(store)
    orig, synth = v["groups"]["originales"], v["groups"]["perturbaciones_sinteticas"]
    assert (orig["label_cited"]["acuerdos"], orig["label_cited"]["n"]) == (28, 30)
    assert (orig["label_context"]["acuerdos"], orig["label_context"]["n"]) == (29, 30)
    for f in D.FIELDS:
        assert (synth[f]["acuerdos"], synth[f]["n"]) == (16, 17)
        assert synth[f]["supported_indebido"] == ["J46"]
        assert synth[f]["kappa_lectura"].startswith("no aplica")
    assert orig["label_context"]["kappa_lectura"].startswith("no informativa")
    assert orig["label_cited"]["kappa_lectura"] is None
    assert orig["label_cited"]["kappa"] == 0.5745
    # La matriz incluye judge_unverifiable como columna (J12 cuenta como desacuerdo).
    corner = D.MATRIX_CORNER
    partial = next(r for r in orig["label_cited"]["matriz"] if r[corner] == "partially_supported")
    assert partial == {
        corner: "partially_supported",
        "supported": 1,
        "partially_supported": 1,
        "judge_unverifiable": 1,
        "total": 3,
    }


def test_all_four_matrices_are_complete_and_rows_sum_to_denominators(store):
    v = D.faithfulness_view(store)
    rep = _report("judge_comparison")
    corner = D.MATRIX_CORNER
    for group, n in (("originales", 30), ("perturbaciones_sinteticas", 17)):
        for f in D.FIELDS:
            s = v["groups"][group][f]
            counts = rep["per_group"][group][f]["confusion_matrix"]["counts"]
            shown_cols = [c for c in s["matriz"][0] if c not in (corner, "total")]
            assert "judge_unverifiable" in shown_cols
            # Ninguna clase con casos queda oculta; solo se omiten clases vacías.
            for ref, row in counts.items():
                for col, val in row.items():
                    if val:
                        assert col in shown_cols and ref in [r[corner] for r in s["matriz"]]
            for col in s["omitidas"]:
                assert all(row.get(col, 0) == 0 for row in counts.values())
            # Cada fila suma su denominador y el total coincide con n.
            for r in s["matriz"]:
                assert r["total"] == sum(counts[r[corner]].values())
                assert r["total"] == sum(r[c] for c in shown_cols)
            assert sum(r["total"] for r in s["matriz"]) == s["n"] == n
    assert v["unverifiable"] == ["J12"] and v["invalid_quotes"] == []
    assert v["run"]["casos"] == 47 and v["run"]["max_completion_tokens"] == 640
    assert v["stability"] == {
        "n": 11,
        "same": {"label_cited": 11, "label_context": 11},
        "changed": [],
    }
    assert sum(r["tipo"] == "sintético" for r in v["per_case"]) == 17


# --- Failure explorer --------------------------------------------------------------------------


def test_featured_cases_show_the_right_texts_and_labels(store):
    j46 = D.case_detail(store, "J46")
    assert j46["afirmacion_juzgada"].startswith("Cambiar a un plan superior no permite")
    assert j46["afirmacion_original"].startswith("Cambiar a un plan superior permite")
    assert j46["revision_humana_perturbacion"] == "si"
    assert [x["resultado"] for x in j46["etiquetas"]] == ["semantic_error"] * 2
    assert all(e["válida"] for e in j46["evidencia_juez"]) and j46["razonamiento_cortado"]

    j12 = D.case_detail(store, "J12")
    cited = j12["etiquetas"][0]
    assert (cited["juez (cruda)"], cited["juez (verificada)"]) == (
        "partially_supported",
        "judge_unverifiable",
    )
    assert cited["resultado"] == "citation_error"
    assert j12["fragmentos_citados"] == ["S1"]
    assert [(e["cite_id"], e["fragmento citado"]) for e in j12["evidencia_juez"]] == [("S3", False)]

    j02 = D.case_detail(store, "J02")
    assert j02["afirmacion_original"] is None
    assert [x["referencia"] for x in j02["etiquetas"]] == ["partially_supported"] * 2
    assert [x["juez (verificada)"] for x in j02["etiquetas"]] == ["supported"] * 2
    for cid in D.FEATURED_CASES:
        assert D.CASE_NOTES[cid]


def test_case_details_match_frozen_predictions(store):
    preds = {p["case_id"]: p for p in store.get("judge_predictions")}
    ids = D.case_ids(store)
    assert len(ids) == 47 and ids[:3] == ["J01", "J02", "J03"]
    for cid in ids:
        d = D.case_detail(store, cid)
        p = preds[cid]
        assert d["afirmacion_juzgada"] == p["claim_text"]
        for lab in d["etiquetas"]:
            assert lab["juez (verificada)"] == p["judge"][lab["campo"]]


# --- Privacidad --------------------------------------------------------------------------------


def test_no_view_exposes_private_identifiers(store):
    views = [D.retrieval_view(store), D.generation_view(store), D.faithfulness_view(store)]
    views += [D.case_detail(store, c) for c in D.case_ids(store)]
    views.append(D.integrity(store))
    for v in views:
        D.assert_no_private_data(v)


@pytest.mark.parametrize(
    "bad",
    [
        {"request_id": "x"},
        {"a": [{"ratelimit": {}}]},
        {"m": "error en organization org_01abcDEF234"},
        {"k": "gsk_abcdef123456"},
    ],
)
def test_privacy_guard_catches_leaks(bad):
    with pytest.raises(AssertionError):
        D.assert_no_private_data(bad)


# --- La app arranca y renderiza cada sección (sin servidor) ------------------------------------


@pytest.mark.parametrize("section", ["Retrieval", "Generación", "Faithfulness", "Failure explorer"])
def test_app_renders_each_section_without_errors(section):
    pytest.importorskip("streamlit")
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(PKG / "app.py"), default_timeout=60).run()
    assert not at.exception
    at.sidebar.radio[0].set_value(section).run()
    assert not at.exception, [e.value for e in at.exception]
    assert at.header[0].value
    text = " ".join(
        [m.value for m in at.markdown]
        + [str(m.value) for m in at.metric]
        + [c.value for c in at.caption]
    )
    for pat in (r"org_", "gsk_", "req_"):
        assert pat not in text
    # Faltantes como "—", nunca "None"; sin indicadores de tendencia en las métricas.
    for t in at.table:
        assert "None" not in t.value.to_string()
    assert all(not m.delta for m in at.metric)
    if section == "Faithfulness":
        matrices = [t.value for t in at.table if D.MATRIX_CORNER in t.value.columns]
        assert len(matrices) == 4
        assert all("judge unverifiable" in m.columns for m in matrices)


def test_faithfulness_page_shows_j12_in_cited_matrix():
    pytest.importorskip("streamlit")
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(PKG / "app.py"), default_timeout=60).run()
    at.sidebar.radio[0].set_value("Faithfulness").run()
    first = next(t.value for t in at.table if D.MATRIX_CORNER in t.value.columns)
    row = first[first[D.MATRIX_CORNER] == "partially supported"].iloc[0]
    assert (row["judge unverifiable"], row["total"]) == ("1", "3")


def test_case_texts_are_shown_literally():
    pytest.importorskip("streamlit")
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(PKG / "app.py"), default_timeout=60).run()
    at.sidebar.radio[0].set_value("Failure explorer").run()
    at.radio[0].set_value("J46").run()
    md = " ".join(m.value for m in at.markdown)
    assert "Afirmación perturbada" in md and "**no permite**" in md
    for e in D.case_detail(D.load_store(), "J46")["evidencia_juez"]:
        assert e["quote"][:40] in md.replace("\\", "")


def test_failure_explorer_navigates_featured_cases():
    pytest.importorskip("streamlit")
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(PKG / "app.py"), default_timeout=60).run()
    at.sidebar.radio[0].set_value("Failure explorer").run()
    for cid in D.FEATURED_CASES:
        at.radio[0].set_value(cid).run()
        assert not at.exception
        assert at.subheader[0].value.startswith(cid)
    at.radio[0].set_value("Otro caso").run()
    assert not at.exception and at.selectbox[0].options
