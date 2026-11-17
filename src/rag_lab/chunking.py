"""Fragmentación por estructura Markdown con offsets trazables.

Reglas (documentadas en docs/metrics.md):
1. El cuerpo se divide en párrafos: líneas consecutivas no vacías que no son encabezados.
2. Cada párrafo pertenece a la sección del último encabezado visto ('#' a '######').
3. Los párrafos de una misma sección se empaquetan en orden mientras el chunk resultante
   (desde el inicio del primer párrafo hasta el fin del último) mida <= max_chars.
   Un chunk nunca cruza secciones.
4. Un párrafo más largo que max_chars se divide por oraciones; una oración más larga
   que max_chars se corta en duros.
5. Invariante: chunk.text == doc.body[chunk.start:chunk.end].
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from rag_lab.corpus import Document

_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    doc_id: str
    ordinal: int
    start: int
    end: int
    section: str
    text: str
    embed_text: str
    status: str
    version: str
    effective_date: str
    superseded_by: str | None

    def to_dict(self) -> dict:
        return dict(self.__dict__)


def _paragraphs(body: str) -> list[tuple[int, int, str]]:
    """Devuelve (start, end, section) por párrafo."""
    out: list[tuple[int, int, str]] = []
    section = ""
    pos = 0
    para_start: int | None = None
    para_end = 0
    para_section = ""
    for line in body.split("\n"):
        line_start, line_end = pos, pos + len(line)
        pos = line_end + 1
        heading = _HEADING.match(line)
        if heading or not line.strip():
            if para_start is not None:
                out.append((para_start, para_end, para_section))
                para_start = None
            if heading:
                section = heading.group(2).strip()
            continue
        if para_start is None:
            para_start, para_section = line_start + (len(line) - len(line.lstrip())), section
        para_end = line_end - (len(line) - len(line.rstrip()))
    if para_start is not None:
        out.append((para_start, para_end, para_section))
    return out


def _split_long(body: str, start: int, end: int, max_chars: int) -> list[tuple[int, int]]:
    """Divide [start, end) por oraciones y, si hace falta, en duros."""
    pieces: list[tuple[int, int]] = []
    s = start
    for m in _SENTENCE_END.finditer(body, start, end):
        pieces.append((s, m.start()))
        s = m.end()
    pieces.append((s, end))
    hard: list[tuple[int, int]] = []
    for a, b in pieces:
        while b - a > max_chars:
            hard.append((a, a + max_chars))
            a += max_chars
        if b > a:
            hard.append((a, b))
    return _pack(hard, max_chars)


def _pack(units: list[tuple[int, int]], max_chars: int) -> list[tuple[int, int]]:
    packed: list[tuple[int, int]] = []
    cur: tuple[int, int] | None = None
    for a, b in units:
        if cur is None:
            cur = (a, b)
        elif b - cur[0] <= max_chars:
            cur = (cur[0], b)
        else:
            packed.append(cur)
            cur = (a, b)
    if cur is not None:
        packed.append(cur)
    return packed


def chunk_document(doc: Document, max_chars: int) -> list[Chunk]:
    if max_chars < 50:
        raise ValueError("max_chars demasiado chico")
    paragraphs = _paragraphs(doc.body)
    spans: list[tuple[int, int, str]] = []
    i = 0
    while i < len(paragraphs):
        section = paragraphs[i][2]
        group = []
        while i < len(paragraphs) and paragraphs[i][2] == section:
            a, b, _ = paragraphs[i]
            group.extend(_split_long(doc.body, a, b, max_chars) if b - a > max_chars else [(a, b)])
            i += 1
        spans.extend((a, b, section) for a, b in _pack(group, max_chars))

    chunks = []
    for ordinal, (a, b, section) in enumerate(spans):
        text = doc.body[a:b]
        header = doc.title if section in ("", doc.title) else f"{doc.title}\n{section}"
        chunks.append(
            Chunk(
                chunk_id=f"{doc.doc_id}#{ordinal:03d}",
                doc_id=doc.doc_id,
                ordinal=ordinal,
                start=a,
                end=b,
                section=section,
                text=text,
                embed_text=f"{header}\n\n{text}",
                status=doc.status,
                version=doc.version,
                effective_date=doc.effective_date,
                superseded_by=doc.superseded_by,
            )
        )
    return chunks


def chunk_corpus(docs: dict[str, Document], max_chars: int) -> list[Chunk]:
    chunks: list[Chunk] = []
    for doc_id in sorted(docs):
        chunks.extend(chunk_document(docs[doc_id], max_chars))
    return chunks
