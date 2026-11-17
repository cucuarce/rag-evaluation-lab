"""Context builder: fragmentos recuperados -> bloque de evidencia con metadatos de vigencia.

Entrada: resultados de retrieval (chunk_ids en orden) + chunks.jsonl del índice + corpus.
Cada fragmento recibe un ID corto de cita (S1..Sk) que se mapea al chunk_id real.
No recibe ni puede recibir etiquetas de evaluación.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from rag_lab.corpus import Document


@dataclass(frozen=True)
class ContextChunk:
    cite_id: str  # "S1".."Sk": lo que el modelo usa para citar
    chunk_id: str
    doc_id: str
    title: str
    section: str
    version: str
    status: str  # "active" | "deprecated"
    effective_date: str
    end_date: str | None
    superseded_by: str | None
    text: str
    start: int
    end: int

    def vigencia(self) -> str:
        if self.status == "active":
            return f"VIGENTE (desde {self.effective_date})"
        until = self.end_date or "fecha no informada"
        repl = f"; reemplazado por {self.superseded_by}" if self.superseded_by else ""
        return f"HISTÓRICO / deprecated (vigente del {self.effective_date} al {until}{repl})"

    def render(self) -> str:
        header = (
            f"[{self.cite_id}] documento: {self.doc_id} | título: {self.title} | "
            f"versión: {self.version} | estado: {self.vigencia()}"
        )
        if self.section:
            header += f" | sección: {self.section}"
        return f"{header}\n{self.text}"

    def to_dict(self) -> dict:
        return {
            "cite_id": self.cite_id,
            "chunk_id": self.chunk_id,
            "doc_id": self.doc_id,
            "status": self.status,
            "version": self.version,
            "start": self.start,
            "end": self.end,
        }


class ChunkStore:
    """Texto y offsets de los chunks del índice (chunks.jsonl), sin cargar modelos."""

    def __init__(self, chunks: dict[str, dict], docs: dict[str, Document]):
        self.chunks = chunks
        self.docs = docs

    @classmethod
    def from_index_dir(cls, index_dir: Path, docs: dict[str, Document]) -> ChunkStore:
        path = index_dir / "chunks.jsonl"
        if not path.exists():
            raise FileNotFoundError(f"No existe {path}; ejecutá `rag-lab index` primero")
        chunks = {}
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                chunks[row["chunk_id"]] = row
        return cls(chunks, docs)

    def build(self, chunk_ids: list[str]) -> list[ContextChunk]:
        out = []
        for i, cid in enumerate(chunk_ids, start=1):
            if cid not in self.chunks:
                raise ValueError(f"chunk inexistente en el índice: {cid}")
            c = self.chunks[cid]
            doc = self.docs[c["doc_id"]]
            out.append(
                ContextChunk(
                    cite_id=f"S{i}",
                    chunk_id=cid,
                    doc_id=c["doc_id"],
                    title=doc.title,
                    section=c["section"],
                    version=doc.version,
                    status=doc.status,
                    effective_date=doc.effective_date,
                    end_date=doc.end_date,
                    superseded_by=doc.superseded_by,
                    text=c["text"],
                    start=c["start"],
                    end=c["end"],
                )
            )
        return out
