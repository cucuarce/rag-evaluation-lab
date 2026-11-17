"""Hashes estables para dejar constancia de corpus, datasets y configuraciones."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    # Normaliza finales de línea para que el hash no dependa de git autocrlf.
    return sha256_bytes(path.read_bytes().replace(b"\r\n", b"\n"))


def sha256_json(obj: object) -> str:
    payload = json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return sha256_bytes(payload.encode("utf-8"))


def sha256_dir(directory: Path, pattern: str = "*.md") -> str:
    """Hash de un directorio: nombres relativos + contenido, en orden determinístico."""
    entries = []
    for p in sorted(directory.glob(pattern)):
        entries.append({"name": p.name, "sha256": sha256_file(p)})
    return sha256_json(entries)
