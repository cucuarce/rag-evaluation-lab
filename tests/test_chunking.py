from __future__ import annotations

from itertools import pairwise
from pathlib import Path

from rag_lab.chunking import chunk_corpus, chunk_document
from rag_lab.corpus import parse_document


def _doc(body: str):
    text = (
        '+++\ndoc_id = "t"\ntitle = "T"\nversion = "1"\neffective_date = "2026-01-01"\n'
        'status = "active"\n+++\n' + body
    )
    return parse_document(text, Path("t.md"))


def test_offsets_reproduce_text_for_whole_corpus(docs, cfg_a):
    chunks = chunk_corpus(docs, cfg_a.chunking.max_chars)
    assert chunks
    for c in chunks:
        assert docs[c.doc_id].body[c.start : c.end] == c.text
        assert len(c.text) <= cfg_a.chunking.max_chars
        assert c.text == c.text.strip()
        assert c.embed_text.endswith(c.text)


def test_chunks_are_ordered_non_overlapping_and_carry_metadata(docs, cfg_a):
    chunks = chunk_corpus(docs, cfg_a.chunking.max_chars)
    by_doc: dict[str, list] = {}
    for c in chunks:
        by_doc.setdefault(c.doc_id, []).append(c)
        assert c.status == docs[c.doc_id].status
        assert c.superseded_by == docs[c.doc_id].superseded_by
    for cs in by_doc.values():
        for a, b in pairwise(cs):
            assert a.end <= b.start


def test_chunking_is_deterministic(docs, cfg_a):
    a = chunk_corpus(docs, cfg_a.chunking.max_chars)
    b = chunk_corpus(docs, cfg_a.chunking.max_chars)
    assert [c.to_dict() for c in a] == [c.to_dict() for c in b]


def test_chunk_never_crosses_sections():
    doc = _doc("# T\n\nIntro.\n\n## Uno\n\nPárrafo uno.\n\n## Dos\n\nPárrafo dos.\n")
    chunks = chunk_document(doc, max_chars=500)
    assert [c.section for c in chunks] == ["T", "Uno", "Dos"]
    assert [c.text for c in chunks] == ["Intro.", "Párrafo uno.", "Párrafo dos."]


def test_paragraphs_of_same_section_are_packed_until_limit():
    body = "# T\n\n## S\n\n" + "\n\n".join(["a" * 40] * 3) + "\n"
    doc = _doc(body)
    packed = chunk_document(doc, max_chars=100)  # 40 + 2 + 40 = 82 <= 100; +42 > 100
    assert [len(c.text) for c in packed] == [82, 40]
    for c in packed:
        assert doc.body[c.start : c.end] == c.text


def test_long_paragraph_is_split_by_sentences_then_hard():
    sentence = "Esta es una oración de prueba."  # 30 chars
    body = "# T\n\n" + " ".join([sentence] * 5) + "\n\n" + "x" * 130 + "\n"
    doc = _doc(body)
    chunks = chunk_document(doc, max_chars=70)
    assert all(len(c.text) <= 70 for c in chunks)
    assert chunks[0].text == f"{sentence} {sentence}"
    for c in chunks:
        assert doc.body[c.start : c.end] == c.text
    assert "".join(c.text for c in chunks[-2:]) == "x" * 130
