"""Carga de preguntas. Es lo ÚNICO del dataset que ve el pipeline de retrieval.

El esquema es estricto: cada línea debe tener exactamente {qid, question}. Cualquier campo
extra (por ejemplo una respuesta de referencia pegada por error) hace fallar la carga.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

ALLOWED_KEYS = {"qid", "question"}


@dataclass(frozen=True)
class Question:
    qid: str
    question: str


def load_questions(path: Path) -> list[Question]:
    out: list[Question] = []
    seen: set[str] = set()
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        row = json.loads(line)
        if set(row) != ALLOWED_KEYS:
            raise ValueError(
                f"{path.name}:{lineno}: se esperaban exactamente {sorted(ALLOWED_KEYS)}, "
                f"se encontró {sorted(row)}"
            )
        if row["qid"] in seen:
            raise ValueError(f"{path.name}:{lineno}: qid duplicado {row['qid']}")
        if not row["question"].strip():
            raise ValueError(f"{path.name}:{lineno}: pregunta vacía")
        seen.add(row["qid"])
        out.append(Question(qid=row["qid"], question=row["question"]))
    return out
