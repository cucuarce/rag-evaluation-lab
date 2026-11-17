"""Validación de corpus y datasets (no requiere modelo ni índice)."""

from __future__ import annotations

import re
from collections import Counter

from rag_lab.chunking import chunk_corpus
from rag_lab.config import ExperimentConfig
from rag_lab.corpus import load_corpus
from rag_lab.evaluation.labels import load_labels
from rag_lab.evaluation.metrics import covers
from rag_lab.questions import load_questions
from rag_lab.runner import SPLITS, split_paths
from rag_lab.text import strip_accents

EXPECTED = {
    "eval": {"single": 14, "multi_hop": 8, "distractor": 8, "unanswerable": 10},
    "calibration": {"single": 4, "multi_hop": 2, "distractor": 2, "unanswerable": 2},
}


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", strip_accents(text).lower()).strip()


def validate_data(cfg: ExperimentConfig) -> dict:
    """Lanza ValueError ante errores; devuelve un reporte con advertencias informativas."""
    docs = load_corpus(cfg.corpus_dir)
    chunks = chunk_corpus(docs, cfg.chunking.max_chars)
    tau = cfg.evaluation.span_coverage_threshold
    errors: list[str] = []
    report: dict = {
        "n_documents": len(docs),
        "documents_by_status": dict(Counter(d.status for d in docs.values())),
        "n_chunks": len(chunks),
        "splits": {},
    }

    seen_q: dict[str, str] = {}
    for split in SPLITS:
        q_path, l_path = split_paths(split)
        questions = load_questions(q_path)
        labels = load_labels(l_path, docs)
        qids = {q.qid for q in questions}
        if qids != set(labels):
            errors.append(
                f"{split}: qids de preguntas y etiquetas difieren: {sorted(qids ^ set(labels))}"
            )
        counts = dict(Counter(lab.category for lab in labels.values()))
        if counts != EXPECTED[split]:
            errors.append(f"{split}: distribución {counts} != esperada {EXPECTED[split]}")

        for q in questions:
            key = _norm(q.question)
            if q.qid in seen_q or key in seen_q.values():
                errors.append(f"{q.qid}: qid o texto repetido entre splits")
            seen_q[q.qid] = key
            lab = labels.get(q.qid)
            if lab and lab.answerable and _norm(lab.reference_answer) in key:
                errors.append(f"{q.qid}: la respuesta de referencia aparece en la pregunta")

        split_spans_multi_chunk = []
        shared_gold_distractor = []
        deprecated_gold = []
        for lab in labels.values():
            for req in lab.gold:
                for s in req.alternatives:
                    covering = [c for c in chunks if covers(c, s, tau)]
                    if not covering:
                        errors.append(f"{lab.qid}/{req.id}: ningún chunk cubre >= {tau} de la cita")
                    if not any(
                        c.doc_id == s.doc_id and c.start <= s.start and s.end <= c.end
                        for c in chunks
                    ):
                        split_spans_multi_chunk.append(f"{lab.qid}/{req.id}")
                    if docs[s.doc_id].status == "deprecated":
                        deprecated_gold.append(lab.qid)
            for d in lab.distractors:
                d_chunks = {c.chunk_id for c in chunks if covers(c, d, tau)}
                g_chunks = {
                    c.chunk_id
                    for r in lab.gold
                    for s in r.alternatives
                    for c in chunks
                    if covers(c, s, tau)
                }
                if d_chunks & g_chunks:
                    shared_gold_distractor.append(lab.qid)
        report["splits"][split] = {
            "n_questions": len(questions),
            "categories": counts,
            "gold_spans_not_inside_single_chunk": split_spans_multi_chunk,
            "questions_with_gold_in_deprecated_doc": sorted(set(deprecated_gold)),
            "distractor_shares_chunk_with_gold": sorted(set(shared_gold_distractor)),
        }
    if errors:
        raise ValueError("Validación fallida:\n  - " + "\n  - ".join(errors))
    return report
