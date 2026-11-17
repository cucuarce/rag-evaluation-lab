"""Gate de abstención basado en evidencia (sin etiquetas).

Score del gate (definido por método de retrieval, porque los scores NO son equivalentes):
- dense : coseno exacto del chunk top-1 (e5-small, normalizado). Rango práctico ~[0.8, 0.95].
- hybrid: el score RRF solo refleja rangos (máx. 2/61 ≈ 0.0328 para cualquier pregunta), no
          fuerza de evidencia. Se usa el MÁXIMO coseno dense entre los k chunks entregados
          al generador (details.dense_score). Chunks sin rango dense (fuera del top-50)
          no aportan.
Regla: si score < umbral -> abstención por gate (no se llama al LLM).

El umbral se calibra por configuración de retrieval, SOLO con el split calibration
(rag_lab.evaluation.gate_calibration) y se guarda en reports/gate_<run>.json.
"""

from __future__ import annotations

import json
from pathlib import Path


def gate_score(results: list[dict], method: str) -> float | None:
    if not results:
        return None
    if method == "dense":
        return float(results[0]["score"])
    if method == "hybrid":
        dense = [r["details"].get("dense_score") for r in results]
        dense = [d for d in dense if d is not None]
        return float(max(dense)) if dense else None
    raise ValueError(f"método de retrieval sin gate definido: {method!r}")


def load_gate(path: Path, run_manifest: dict) -> dict:
    """Carga el umbral y verifica que corresponda a esta configuración y al split calibration."""
    if not path.exists():
        raise FileNotFoundError(
            f"No existe {path}. Calibrá primero: rag-lab calibrate-gate "
            f"runs/calibration/{run_manifest['run_name']}"
        )
    gate = json.loads(path.read_text(encoding="utf-8"))
    if gate["calibration_split"] != "calibration":
        raise ValueError("el umbral del gate debe provenir del split calibration")
    method = run_manifest["config"]["retrieval"]["method"]
    checks = {
        "retrieval_run_name": run_manifest["run_name"],
        "method": method,
        "index_id": run_manifest["index_id"],
        "retrieval_config_hash": run_manifest["config_hash"],
    }
    for key, expected in checks.items():
        if gate[key] != expected:
            raise ValueError(f"gate incompatible: {key}={gate[key]!r} != {expected!r}")
    return gate
