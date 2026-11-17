"""Etiquetas de evaluación. Solo las importa el paquete `rag_lab.evaluation`.

La evidencia se etiqueta como citas textuales (`quote`) dentro de un documento, no como IDs
de chunk. Cada cita debe aparecer exactamente una vez en el cuerpo del documento y se
resuelve a offsets [start, end). Así las etiquetas sobreviven a cambios de chunking.

Una pregunta tiene una lista de *requisitos* de evidencia (`gold_evidence`). Cada requisito
tiene una o más citas alternativas: el requisito se satisface si se recupera cualquiera.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from rag_lab.corpus import Document

CATEGORIES = {"single", "multi_hop", "distractor", "unanswerable"}
LABEL_KEYS = {
    "qid",
    "category",
    "answerable",
    "gold_evidence",
    "distractor_evidence",
    "reference_answer",
    "required_facts",
    "forbidden_facts",
    "notes",
}


@dataclass(frozen=True)
class Span:
    doc_id: str
    start: int
    end: int
    quote: str

    def __len__(self) -> int:
        return self.end - self.start


@dataclass(frozen=True)
class Requirement:
    id: str
    alternatives: tuple[Span, ...]


@dataclass(frozen=True)
class Label:
    qid: str
    category: str
    answerable: bool
    gold: tuple[Requirement, ...]
    distractors: tuple[Span, ...]
    reference_answer: str
    required_facts: tuple[str, ...]
    forbidden_facts: tuple[str, ...]
    notes: str


def resolve_quote(docs: dict[str, Document], doc_id: str, quote: str, where: str) -> Span:
    doc = docs.get(doc_id)
    if doc is None:
        raise ValueError(f"{where}: doc_id inexistente {doc_id!r}")
    if not quote.strip():
        raise ValueError(f"{where}: cita vacía")
    first = doc.body.find(quote)
    if first < 0:
        raise ValueError(f"{where}: la cita no aparece en {doc_id}: {quote[:60]!r}")
    if doc.body.find(quote, first + 1) >= 0:
        raise ValueError(f"{where}: la cita aparece más de una vez en {doc_id}: {quote[:60]!r}")
    return Span(doc_id=doc_id, start=first, end=first + len(quote), quote=quote)


def _parse_label(row: dict, docs: dict[str, Document], where: str) -> Label:
    if set(row) != LABEL_KEYS:
        raise ValueError(f"{where}: claves {sorted(row)} != {sorted(LABEL_KEYS)}")
    if row["category"] not in CATEGORIES:
        raise ValueError(f"{where}: categoría inválida {row['category']!r}")
    answerable = row["answerable"]
    if answerable != (row["category"] != "unanswerable"):
        raise ValueError(f"{where}: answerable inconsistente con la categoría")
    gold = []
    req_ids = set()
    for req in row["gold_evidence"]:
        if req["id"] in req_ids:
            raise ValueError(f"{where}: id de requisito duplicado {req['id']}")
        req_ids.add(req["id"])
        if not req["spans"]:
            raise ValueError(f"{where}: requisito {req['id']} sin citas")
        alts = tuple(
            resolve_quote(docs, s["doc_id"], s["quote"], f"{where}/{req['id']}")
            for s in req["spans"]
        )
        gold.append(Requirement(id=req["id"], alternatives=alts))
    if answerable and not gold:
        raise ValueError(f"{where}: pregunta respondible sin evidencia")
    if not answerable and (gold or row["distractor_evidence"]):
        raise ValueError(f"{where}: pregunta no respondible con evidencia etiquetada")
    if row["category"] == "multi_hop" and len(gold) < 2:
        raise ValueError(f"{where}: multi_hop requiere >= 2 requisitos de evidencia")
    if row["category"] == "distractor" and not row["distractor_evidence"]:
        raise ValueError(f"{where}: categoría distractor sin distractor_evidence")
    distractors = tuple(
        resolve_quote(docs, s["doc_id"], s["quote"], f"{where}/distractor")
        for s in row["distractor_evidence"]
    )
    gold_spans = {(s.doc_id, s.start, s.end) for r in gold for s in r.alternatives}
    if any((d.doc_id, d.start, d.end) in gold_spans for d in distractors):
        raise ValueError(f"{where}: una cita es gold y distractor a la vez")
    return Label(
        qid=row["qid"],
        category=row["category"],
        answerable=answerable,
        gold=tuple(gold),
        distractors=distractors,
        reference_answer=row["reference_answer"],
        required_facts=tuple(row["required_facts"]),
        forbidden_facts=tuple(row["forbidden_facts"]),
        notes=row["notes"],
    )


def load_labels(path: Path, docs: dict[str, Document]) -> dict[str, Label]:
    labels: dict[str, Label] = {}
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        row = json.loads(line)
        where = f"{path.name}:{lineno}({row.get('qid')})"
        label = _parse_label(row, docs, where)
        if label.qid in labels:
            raise ValueError(f"{where}: qid duplicado")
        labels[label.qid] = label
    return labels
