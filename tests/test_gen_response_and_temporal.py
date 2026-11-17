from __future__ import annotations

import json

import pytest

from rag_lab.config import PROJECT_ROOT
from rag_lab.corpus import load_corpus
from rag_lab.generation.context import ChunkStore
from rag_lab.generation.prompt import ANSWER_SCHEMA, build_prompt
from rag_lab.generation.response import parse_answer
from rag_lab.generation.temporal import classify_temporal_scope
from rag_lab.questions import load_questions
from rag_lab.runner import split_paths

REF = "2026-11-01"
ALLOWED = ["S1", "S2", "S3"]


def _j(**kw):
    base = {"answer": "x", "citations": ["S1"], "abstain": False, "abstain_reason": "none"}
    return json.dumps(base | kw)


# --- JSON / esquema -------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "error_prefix"),
    [
        (None, "empty_response"),
        ("", "empty_response"),
        ("no es json", "invalid_json"),
        ("[1, 2]", "not_an_object"),
        (json.dumps({"answer": "x", "citations": []}), "keys"),
        (_j(abstain="no"), "abstain no es booleano"),
        (_j(abstain_reason="otra"), "abstain_reason inválido"),
        (_j(citations="S1"), "citations no es lista"),
        (_j(answer=3), "answer no es string"),
    ],
)
def test_invalid_responses_are_format_errors(raw, error_prefix):
    p = parse_answer(raw, ALLOWED)
    assert not p.format_ok
    assert p.format_error.startswith(error_prefix)


def test_valid_response_and_citation_normalization():
    p = parse_answer(_j(citations=["S2", "[S1]", "S2"]), ALLOWED)
    assert p.format_ok and p.valid_citations == ("S2", "S1") and not p.invalid_citations


def test_citations_to_unsupplied_fragments_are_recorded_as_invalid():
    p = parse_answer(_j(citations=["S1", "S9", "politica-reembolsos-v3#001"]), ALLOWED)
    assert p.valid_citations == ("S1",)
    assert p.invalid_citations == ("S9", "politica-reembolsos-v3#001")


def test_answer_without_valid_citations_is_flagged():
    p = parse_answer(_j(citations=["S7"]), ALLOWED)
    assert "respuesta_sin_citas_validas" in p.consistency_issues


def test_inconsistent_abstention_fields_are_flagged():
    p = parse_answer(_j(abstain=True, abstain_reason="none", citations=[]), ALLOWED)
    assert "abstain_true_sin_motivo" in p.consistency_issues


def test_schema_is_strict_mode_compatible():
    assert ANSWER_SCHEMA["additionalProperties"] is False
    assert set(ANSWER_SCHEMA["required"]) == set(ANSWER_SCHEMA["properties"])


# --- regla temporal ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("question", "kind"),
    [
        (
            "¿Cuál era el plazo para pedir el reembolso antes de marzo de 2026?",
            "historical_anchored",
        ),
        ("¿Qué decía la versión 2 de la política de reembolsos?", "historical_anchored"),
        ("¿Cómo era la política anterior?", "historical_anchored"),
        ("¿Cuántos usuarios incluía Pro en 2025?", "historical_anchored"),
        ("¿Cuál era el plazo de reembolso?", "historical_unanchored"),
        ("¿Cuántos días tiene un cliente para pedir el reembolso?", "current"),
        ("¿Qué cambia antes de 2027?", "current"),  # fecha futura respecto de la referencia
        ("¿Cómo verifico que un webhook fue enviado por Kestrel?", "current"),
    ],
)
def test_temporal_rule(question, kind):
    assert classify_temporal_scope(question, REF).kind == kind


def test_temporal_rule_on_benchmark_questions():
    """Solo e10 menciona un período pasado; el resto (incluidas e06 y e21) es vigente."""
    kinds = {
        q.qid: classify_temporal_scope(q.question, REF).kind
        for split in ("eval", "calibration")
        for q in load_questions(split_paths(split)[0])
    }
    assert kinds["e10"] == "historical_anchored"
    assert kinds["e06"] == kinds["e21"] == kinds["e39"] == "current"
    assert [k for k, v in kinds.items() if v != "current"] == ["e10"]


@pytest.fixture(scope="module")
def store(tmp_path_factory):
    from rag_lab.chunking import chunk_corpus

    docs = load_corpus(PROJECT_ROOT / "data" / "corpus")
    chunks = {c.chunk_id: c.to_dict() for c in chunk_corpus(docs, 700)}
    return ChunkStore(chunks, docs)


def test_context_carries_version_and_status_metadata(store):
    ctx = store.build(["politica-reembolsos-v2#001", "politica-reembolsos-v3#001"])
    assert [c.cite_id for c in ctx] == ["S1", "S2"]
    old, new = (c.render() for c in ctx)
    assert "HISTÓRICO" in old and "2026-02-28" in old and "politica-reembolsos-v3" in old
    assert "VIGENTE (desde 2026-03-01)" in new and "versión: 3" in new


def test_prompt_states_the_temporal_rule(store):
    ctx = store.build(["politica-reembolsos-v2#001", "politica-reembolsos-v3#001"])
    cur = build_prompt("¿plazo?", ctx, classify_temporal_scope("¿plazo?", REF), REF)
    hist_q = "¿Cuál era el plazo antes de marzo de 2026?"
    hist = build_prompt(hist_q, ctx, classify_temporal_scope(hist_q, REF), REF)
    vague_q = "¿Cuál era el plazo?"
    vague = build_prompt(vague_q, ctx, classify_temporal_scope(vague_q, REF), REF)
    assert "sobre lo VIGENTE" in cur and "HISTÓRICA" not in cur.split("FRAGMENTOS")[0]
    assert "la pregunta es HISTÓRICA" in hist and "antes de marzo de 2026" in hist
    assert "needs_temporal_context" in vague


def test_unknown_chunk_is_rejected(store):
    with pytest.raises(ValueError):
        store.build(["no-existe#000"])
