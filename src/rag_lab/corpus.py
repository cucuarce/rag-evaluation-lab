"""Carga del corpus: Markdown con front-matter TOML delimitado por '+++'.

Los offsets de todo el sistema (chunks y spans de evidencia) son índices de caracteres
sobre `Document.body`: el texto que sigue al front-matter, con finales de línea '\n'.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

VALID_STATUS = {"active", "deprecated"}
REQUIRED_KEYS = {"doc_id", "title", "version", "effective_date", "status"}
DELIM = "+++"


@dataclass(frozen=True)
class Document:
    doc_id: str
    title: str
    version: str
    effective_date: str
    status: str
    body: str
    path: Path
    end_date: str | None = None
    supersedes: str | None = None
    superseded_by: str | None = None

    def metadata(self) -> dict:
        return {
            "doc_id": self.doc_id,
            "title": self.title,
            "version": self.version,
            "effective_date": self.effective_date,
            "end_date": self.end_date,
            "status": self.status,
            "supersedes": self.supersedes,
            "superseded_by": self.superseded_by,
        }


def parse_document(text: str, path: Path) -> Document:
    text = text.replace("\r\n", "\n")
    lines = text.split("\n")
    if not lines or lines[0].strip() != DELIM:
        raise ValueError(f"{path.name}: falta el front-matter '+++'")
    try:
        end = next(i for i in range(1, len(lines)) if lines[i].strip() == DELIM)
    except StopIteration as exc:
        raise ValueError(f"{path.name}: front-matter sin cerrar") from exc
    meta = tomllib.loads("\n".join(lines[1:end]))
    missing = REQUIRED_KEYS - meta.keys()
    if missing:
        raise ValueError(f"{path.name}: faltan claves de front-matter {sorted(missing)}")
    unknown = meta.keys() - REQUIRED_KEYS - {"end_date", "supersedes", "superseded_by"}
    if unknown:
        raise ValueError(f"{path.name}: claves desconocidas {sorted(unknown)}")
    if meta["status"] not in VALID_STATUS:
        raise ValueError(f"{path.name}: status inválido {meta['status']!r}")
    body = "\n".join(lines[end + 1 :])
    return Document(body=body, path=path, **meta)


def load_corpus(corpus_dir: Path) -> dict[str, Document]:
    docs: dict[str, Document] = {}
    for path in sorted(corpus_dir.glob("*.md")):
        doc = parse_document(path.read_text(encoding="utf-8"), path)
        if doc.doc_id in docs:
            raise ValueError(f"doc_id duplicado: {doc.doc_id}")
        docs[doc.doc_id] = doc
    if not docs:
        raise ValueError(f"No hay documentos en {corpus_dir}")
    validate_versioning(docs)
    return docs


def validate_versioning(docs: dict[str, Document]) -> None:
    """Reglas de versionado: todo deprecated apunta a una versión vigente y viceversa."""
    for doc in docs.values():
        if doc.status == "deprecated":
            if not doc.superseded_by or not doc.end_date:
                raise ValueError(
                    f"{doc.doc_id}: un documento deprecated requiere superseded_by y end_date"
                )
            successor = docs.get(doc.superseded_by)
            if successor is None:
                raise ValueError(f"{doc.doc_id}: superseded_by apunta a un doc inexistente")
            if successor.supersedes != doc.doc_id:
                raise ValueError(
                    f"{doc.doc_id}: {successor.doc_id} no declara supersedes recíproco"
                )
            if successor.effective_date <= doc.end_date:
                raise ValueError(
                    f"{doc.doc_id}: la versión sucesora empieza antes del fin de vigencia"
                )
        if doc.supersedes:
            prev = docs.get(doc.supersedes)
            if prev is None or prev.superseded_by != doc.doc_id or prev.status != "deprecated":
                raise ValueError(f"{doc.doc_id}: supersedes inconsistente con {doc.supersedes}")
        if doc.status == "active" and doc.superseded_by:
            raise ValueError(f"{doc.doc_id}: un documento activo no puede tener superseded_by")
