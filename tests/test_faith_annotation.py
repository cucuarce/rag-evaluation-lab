"""Respuestas únicas, afirmaciones propuestas, planilla ciega e importación de etiquetas."""

from __future__ import annotations

import csv
import io
import json
import re
import shutil

import pytest

from rag_lab.config import PROJECT_ROOT
from rag_lab.faithfulness.annotation import (
    FILL_COLS,
    build_annotation_sheet,
    import_human_labels,
    import_perturbation_review,
    write_if_unchanged,
)
from rag_lab.faithfulness.answers import collect_unique_answers
from rag_lab.faithfulness.prepare import DEFAULT_GEN_DIRS, prepare
from rag_lab.faithfulness.schema import ContractError, read_jsonl, validate_claims
from rag_lab.runner import _read_jsonl

STAGE3 = PROJECT_ROOT / "data/stage3"


@pytest.fixture(scope="module")
def answers():
    return {a["answer_id"]: a for a in read_jsonl(STAGE3 / "answers.jsonl")}


@pytest.fixture(scope="module")
def claims():
    return read_jsonl(STAGE3 / "claims_proposed.jsonl")


def test_unique_answers_keep_traceability_to_both_runs():
    ans, prov = collect_unique_answers(DEFAULT_GEN_DIRS)
    assert len(ans) == 54
    assert sum(len(a["occurrences"]) for a in ans) == 57  # 29 de A + 28 de B
    shared = sorted(a["qid"] for a in ans if len(a["occurrences"]) == 2)
    assert shared == ["e02", "e21", "e32"]
    assert {s["run"] for s in prov["sources"]} == {"A_dense_k5", "B_hybrid_k5"}
    # Cada ocurrencia corresponde a una generación guardada con esa misma respuesta.
    for a in ans:
        for o in a["occurrences"]:
            gens = {
                g["qid"]: g for g in _read_jsonl(PROJECT_ROOT / o["gen_dir"] / "generations.jsonl")
            }
            g = gens[a["qid"]]
            assert g["answer"] == a["answer"] and g["prompt_sha256"] == o["prompt_sha256"]


def test_committed_stage3_files_are_reproducible(tmp_path):
    shutil.copy(STAGE3 / "claims_proposed.jsonl", tmp_path / "claims_proposed.jsonl")
    m = prepare(out_dir=tmp_path)
    for rel in ("answers.jsonl", "perturbations.jsonl", "annotation/annotation_packet.md"):
        assert (tmp_path / rel).read_bytes() == (STAGE3 / rel).read_bytes(), rel
    committed = json.loads((STAGE3 / "stage3a_manifest.json").read_text("utf-8"))
    assert m["claims"] == committed["claims"] | {"path": m["claims"]["path"]}
    assert m["judge_contract"] == committed["judge_contract"]


def test_claims_are_valid_and_unlabeled(claims, answers):
    validate_claims(claims, answers)
    assert 20 <= len(claims) <= 30
    for c in claims:
        assert c["status"] == "proposed_unreviewed"
        assert not {"label", "label_cited", "label_context"} & set(c)
    subtypes = {s for c in claims for s in c["subtypes"]}
    assert {"numeric", "negation", "derived", "version", "multi_hop"} <= subtypes


def test_claim_validation_rejects_bad_span(claims, answers):
    bad = [dict(claims[0], answer_span="texto que no está en la respuesta")]
    with pytest.raises(ContractError):
        validate_claims(bad, answers)


def test_sheet_is_blind(claims, answers):
    text = build_annotation_sheet(claims, answers)
    header = text.split("\n", 1)[0]
    for forbidden in ("run", "reference", "required", "forbidden", "selection", "judge"):
        assert forbidden not in header
    assert "A_dense" not in text and "B_hybrid" not in text
    for c in claims:  # los IDs tampoco revelan la corrida
        assert re.fullmatch(r"e\d{2}-c\d+", c["claim_id"]), c["claim_id"]
    labels = _read_jsonl(PROJECT_ROOT / "data/eval/labels.jsonl")
    for lab in labels:
        if lab["notes"]:
            assert lab["notes"] not in text
    for c in claims:
        assert c["selection_reason"] not in text


def _filled_sheet(claims, answers, fill):
    rows = list(csv.DictReader(io.StringIO(build_annotation_sheet(claims, answers)), delimiter=";"))
    for r in rows:
        r.update(fill(r))
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=list(rows[0]), delimiter=";", lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
    return buf.getvalue()


def _ok_fill(r):
    first_cited = r["cited_ids"].split(",")[0]
    return {
        "split_decision": "aceptar",
        "label_cited": "Supported",  # mayúsculas toleradas
        "label_context": "supported",
        "support_cite_ids": first_cited,
        "version_issue": "sí",  # tilde tolerada
        "annotator": "h1",
    }


def test_import_round_trip(tmp_path, claims, answers):
    sheet = tmp_path / "s.csv"
    sheet.write_text(_filled_sheet(claims, answers, _ok_fill), encoding="utf-8-sig")
    by_id = {c["claim_id"]: c for c in claims}
    res = import_human_labels(sheet, by_id, answers, round_=1)
    assert len(res["labels"]) == len(claims) and res["pending"] == []
    row = res["labels"][0]
    assert row["label_cited"] == "supported" and row["version_issue"] == "si"
    assert row["source"] == "human" and row["runs"] == by_id[row["claim_id"]]["runs"]


def test_import_keeps_blank_rows_pending(tmp_path, claims, answers):
    sheet = tmp_path / "s.csv"
    sheet.write_text(_filled_sheet(claims, answers, lambda r: {}), encoding="utf-8-sig")
    res = import_human_labels(sheet, {c["claim_id"]: c for c in claims}, answers, 1)
    assert res["labels"] == [] and len(res["pending"]) == len(claims)


@pytest.mark.parametrize(
    "override",
    [
        {"label_cited": "yes"},
        {"split_decision": "tal vez"},
        {"split_decision": "editar"},  # sin claim_text_final
        {"label_cited": "supported", "label_context": "unsupported"},  # incoherente
        {"support_cite_ids": ""},
        {"support_cite_ids": "S9"},
        {"annotator": ""},
        {"version_issue": "quizás"},
        {"subtypes_final": "inventado"},
    ],
)
def test_import_rejects_invalid_rows_and_writes_nothing(tmp_path, claims, answers, override):
    sheet = tmp_path / "s.csv"
    first = claims[0]["claim_id"]
    sheet.write_text(
        _filled_sheet(
            claims, answers, lambda r: _ok_fill(r) | (override if r["claim_id"] == first else {})
        ),
        encoding="utf-8-sig",
    )
    with pytest.raises(ContractError):
        import_human_labels(sheet, {c["claim_id"]: c for c in claims}, answers, 1)


def test_rejected_split_needs_no_labels(tmp_path, claims, answers):
    first = claims[0]["claim_id"]
    sheet = tmp_path / "s.csv"
    sheet.write_text(
        _filled_sheet(
            claims,
            answers,
            lambda r: (
                {"split_decision": "rechazar", "annotator": "h1"}
                if r["claim_id"] == first
                else _ok_fill(r)
            ),
        ),
        encoding="utf-8-sig",
    )
    res = import_human_labels(sheet, {c["claim_id"]: c for c in claims}, answers, 1)
    row = next(r for r in res["labels"] if r["claim_id"] == first)
    assert row["split_decision"] == "rechazar" and row["label_cited"] == ""


def test_sheet_columns_to_fill_are_empty_in_export(claims, answers):
    rows = list(csv.DictReader(io.StringIO(build_annotation_sheet(claims, answers)), delimiter=";"))
    assert all(not r[c] for r in rows for c in FILL_COLS)


def test_write_if_unchanged_protects_annotated_sheet(tmp_path):
    p = tmp_path / "a.csv"
    assert write_if_unchanged(p, "x\n", force=False) == "escrito"
    assert write_if_unchanged(p, "x\n", force=False) == "sin cambios"
    p.write_text("x;anotado\n", encoding="utf-8-sig")
    with pytest.raises(FileExistsError):
        write_if_unchanged(p, "x\n", force=False)
    assert write_if_unchanged(p, "x\n", force=True) == "escrito"


def test_perturbation_review_import(tmp_path):
    perts = {p["pert_id"]: p for p in read_jsonl(STAGE3 / "perturbations.jsonl")}
    pid = next(iter(perts))
    sheet = tmp_path / "p.csv"
    sheet.write_text(
        f"pert_id;human_confirms_expected;notes;annotator\n{pid};Sí;;h1\n", encoding="utf-8"
    )
    res = import_perturbation_review(sheet, perts)
    assert res["reviews"][0]["human_confirms_expected"] == "si"
    sheet.write_text(f"pert_id;human_confirms_expected;notes;annotator\n{pid};x;;h1\n", "utf-8")
    with pytest.raises(ContractError):
        import_perturbation_review(sheet, perts)
