"""Lectura de GROQ_API_KEY desde el entorno o un .env local (ignorado por git).

La clave nunca se imprime, no entra en manifiestos, caché ni reportes. `redact` se aplica
como defensa adicional a cualquier texto de error antes de escribirlo.
"""

from __future__ import annotations

import os
from pathlib import Path

from rag_lab.config import PROJECT_ROOT

KEY_NAME = "GROQ_API_KEY"


def read_dotenv(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip().removeprefix("export ").strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        out[key] = value
    return out


def get_api_key(env_file: Path | None = None) -> str | None:
    """Prioridad: variable de entorno > .env en la raíz del proyecto."""
    value = os.environ.get(KEY_NAME)
    if value:
        return value.strip()
    value = read_dotenv(env_file or PROJECT_ROOT / ".env").get(KEY_NAME)
    return value.strip() if value else None


def key_status(env_file: Path | None = None) -> dict:
    """Información segura sobre la clave (nunca su valor ni fragmentos)."""
    in_env = bool(os.environ.get(KEY_NAME))
    in_file = bool(read_dotenv(env_file or PROJECT_ROOT / ".env").get(KEY_NAME))
    return {
        "present": in_env or in_file,
        "source": "env" if in_env else ("dotenv" if in_file else None),
    }


def redact(text: str, secret: str | None) -> str:
    if secret and secret in text:
        return text.replace(secret, "[REDACTED]")
    return text
