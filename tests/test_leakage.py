"""El pipeline de retrieval no puede ver respuestas ni etiquetas de referencia."""

from __future__ import annotations

import ast
import json

import pytest

import rag_lab.evaluation.labels as labels_mod
from rag_lab.config import PROJECT_ROOT
from rag_lab.questions import load_questions
from rag_lab.retrieval import RetrievedChunk
from rag_lab.runner import retrieve_split, split_paths

SRC = PROJECT_ROOT / "src" / "rag_lab"
RETRIEVAL_SIDE = [
    "chunking.py",
    "corpus.py",
    "embeddings.py",
    "index.py",
    "questions.py",
    "retrieval.py",
    "text.py",
]


@pytest.mark.parametrize("split", ["eval", "calibration"])
def test_questions_files_only_contain_qid_and_question(split):
    for line in split_paths(split)[0].read_text(encoding="utf-8").splitlines():
        assert set(json.loads(line)) == {"qid", "question"}


def test_load_questions_rejects_extra_fields(tmp_path):
    p = tmp_path / "q.jsonl"
    p.write_text(
        json.dumps({"qid": "x", "question": "¿?", "reference_answer": "42"}) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError):
        load_questions(p)


@pytest.mark.parametrize("module", RETRIEVAL_SIDE)
def test_retrieval_side_modules_do_not_import_evaluation(module):
    tree = ast.parse((SRC / module).read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    assert not any(m.startswith("rag_lab.evaluation") or m == "rag_lab.runner" for m in imported)


class RecordingRetriever:
    name = "fake"
    score_type = "none"

    def __init__(self):
        self.queries: list[str] = []

    def retrieve(self, query: str, k: int):
        self.queries.append(query)
        return [
            RetrievedChunk(
                rank=1, chunk_id="c#000", doc_id="c", start=0, end=1, status="active", score=0.0
            )
        ]


@pytest.mark.parametrize("split", ["eval", "calibration"])
def test_retrieval_phase_sees_only_question_text_and_never_loads_labels(split, monkeypatch):
    def boom(*a, **k):
        raise AssertionError("la fase de retrieval intentó leer etiquetas")

    monkeypatch.setattr(labels_mod, "load_labels", boom)
    retriever = RecordingRetriever()
    rows = retrieve_split(split_paths(split)[0], retriever, k=5)
    questions = [q.question for q in load_questions(split_paths(split)[0])]
    assert retriever.queries == questions
    assert all(
        set(r) == {"qid", "question", "retriever", "score_type", "k", "results"} for r in rows
    )


def test_splits_are_disjoint():
    eval_q = load_questions(split_paths("eval")[0])
    cal_q = load_questions(split_paths("calibration")[0])
    assert not {q.qid for q in eval_q} & {q.qid for q in cal_q}
    assert not {q.question for q in eval_q} & {q.question for q in cal_q}
