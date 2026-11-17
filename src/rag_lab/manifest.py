"""Metadatos de entorno para dejar constancia de cada corrida."""

from __future__ import annotations

import platform
import subprocess
import sys
from importlib import metadata

from rag_lab.config import PROJECT_ROOT
from rag_lab.hashing import sha256_file

TRACKED_PACKAGES = (
    "chromadb",
    "sentence-transformers",
    "transformers",
    "tokenizers",
    "torch",
    "numpy",
    "rank-bm25",
    "huggingface-hub",
)


def package_versions() -> dict[str, str | None]:
    out = {}
    for name in TRACKED_PACKAGES:
        try:
            out[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            out[name] = None
    return out


def git_commit() -> str | None:
    try:
        res = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return res.stdout.strip() if res.returncode == 0 else None


def environment() -> dict:
    lock = PROJECT_ROOT / "uv.lock"
    try:
        import torch

        torch_threads = torch.get_num_threads()
    except ImportError:
        torch_threads = None
    return {
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "torch_num_threads": torch_threads,
        "packages": package_versions(),
        "uv_lock_sha256": sha256_file(lock) if lock.exists() else None,
        "git_commit": git_commit(),
    }
