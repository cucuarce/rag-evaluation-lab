"""El generador nunca ve labels.jsonl, reference_answer, required_facts ni forbidden_facts."""

from __future__ import annotations

import ast
import inspect
import json

import pytest

import rag_lab.evaluation.labels as labels_mod
from rag_lab.config import PROJECT_ROOT
from rag_lab.generation import prompt as prompt_mod
from rag_lab.generation.runner import run_generation
from rag_lab.questions import load_questions
from rag_lab.runner import split_paths
from tests.gen_helpers import ScriptedGenerator, fake_cfg, make_retrieval_run, ok_result

GEN_DIR = PROJECT_ROOT / "src" / "rag_lab" / "generation"


@pytest.mark.parametrize("path", sorted(GEN_DIR.glob("*.py")), ids=lambda p: p.name)
def test_generation_modules_do_not_import_evaluation(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    assert not any(m.startswith("rag_lab.evaluation") for m in imported), imported
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    names |= {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    assert not names & {"load_labels", "split_paths"}


def test_prompt_builder_only_accepts_question_context_scope_and_date():
    params = list(inspect.signature(prompt_mod.build_prompt).parameters)
    assert params == ["question", "context", "scope", "reference_date"]


def _eval_label_rows():
    return [
        json.loads(x)
        for x in split_paths("eval")[1].read_text(encoding="utf-8").splitlines()
        if x.strip()
    ]


def test_run_generation_never_loads_labels_and_prompts_have_no_reference_data(
    tmp_path, monkeypatch
):
    def boom(*a, **k):
        raise AssertionError("la generación intentó leer etiquetas")

    monkeypatch.setattr(labels_mod, "load_labels", boom)
    questions = load_questions(split_paths("eval")[0])
    rows = [
        (q.qid, q.question, ["politica-reembolsos-v2#001", "politica-reembolsos-v3#001"], 0.9)
        for q in questions
    ]
    run, index_root = make_retrieval_run(tmp_path, rows)
    gen = ScriptedGenerator(
        [
            ok_result(
                {"answer": "x", "citations": ["S1"], "abstain": False, "abstain_reason": "none"}
            )
        ]
    )
    cfg = fake_cfg()
    cfg = cfg.__class__(**{**cfg.__dict__, "gate_enabled": False})
    out = run_generation(run, cfg, gen, out_dir=tmp_path / "gen", index_root=index_root)

    assert len(gen.prompts) == 40
    labels = _eval_label_rows()
    for prompt in gen.prompts:
        for lab in labels:
            # La respuesta de referencia y las notas nunca aparecen en el prompt.
            assert lab["reference_answer"] not in prompt
            if lab["notes"]:
                assert lab["notes"] not in prompt
        for key in ("reference_answer", "required_facts", "forbidden_facts", "gold_evidence"):
            assert key not in prompt
    text = (out / "generations.jsonl").read_text(encoding="utf-8")
    assert "reference_answer" not in text and "required_facts" not in text


def test_generation_output_does_not_contain_api_key(tmp_path):
    from rag_lab.generation.credentials import redact

    assert redact("error con gsk_SECRETO123 adentro", "gsk_SECRETO123") == (
        "error con [REDACTED] adentro"
    )
