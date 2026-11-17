from __future__ import annotations

from dataclasses import dataclass

import pytest

from rag_lab.config import PROJECT_ROOT, load_config
from rag_lab.corpus import load_corpus
from rag_lab.evaluation.labels import Label, Requirement, Span

CONFIG_A = PROJECT_ROOT / "configs" / "a_dense_k5.toml"
CONFIG_B = PROJECT_ROOT / "configs" / "b_hybrid_k5.toml"


@pytest.fixture(scope="session")
def cfg_a():
    return load_config(CONFIG_A)


@pytest.fixture(scope="session")
def cfg_b():
    return load_config(CONFIG_B)


@pytest.fixture(scope="session")
def docs(cfg_a):
    return load_corpus(cfg_a.corpus_dir)


@dataclass(frozen=True)
class FakeChunk:
    chunk_id: str
    doc_id: str
    start: int
    end: int
    status: str = "active"


def span(doc_id: str, start: int, end: int) -> Span:
    return Span(doc_id=doc_id, start=start, end=end, quote="x" * (end - start))


def label(
    gold: list[list[Span]], distractors: list[Span] | None = None, category: str = "single"
) -> Label:
    return Label(
        qid="t1",
        category=category,
        answerable=True,
        gold=tuple(
            Requirement(id=f"ev{i + 1}", alternatives=tuple(alts)) for i, alts in enumerate(gold)
        ),
        distractors=tuple(distractors or []),
        reference_answer="",
        required_facts=(),
        forbidden_facts=(),
        notes="",
    )
