"""Acuerdo entre dos evaluadores (humano vs juez, o humano vs humano) por afirmación.

- Matriz de confusión: filas = referencia (humano), columnas = evaluado (juez), sobre las 4
  etiquetas más `judge_unverifiable` (solo puede aparecer en el lado del juez).
- Acuerdo observado y kappa de Cohen (4 clases y binaria respaldada / no respaldada). La
  kappa se informa solo con n >= MIN_N_KAPPA y si el acuerdo esperado < 1; si no, `None` con
  el motivo.
- Binario: respaldada = `supported`; todo lo demás (incluido partially_supported y
  judge_unverifiable) = no respaldada.
- Casos críticos listados uno por uno: el juez dice `supported` y la persona no.
- Intervalos de Wilson al 95 %. Con muestras chicas son anchos: el reporte lo dice siempre y
  nunca presenta el acuerdo como prueba de confiabilidad.
"""

from __future__ import annotations

import math

from rag_lab.faithfulness.schema import JUDGE_FINAL_LABELS, LABELS

MIN_N_KAPPA = 10
SMALL_SAMPLE_N = 100
Z95 = 1.959964


def wilson(k: int, n: int, z: float = Z95) -> list[float] | None:
    if n == 0:
        return None
    p = k / n
    den = 1 + z * z / n
    center = (p + z * z / (2 * n)) / den
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return [round(max(0.0, center - half), 4), round(min(1.0, center + half), 4)]


def cohen_kappa(pairs: list[tuple[str, str]]) -> tuple[float | None, str | None]:
    n = len(pairs)
    if n < MIN_N_KAPPA:
        return None, f"n={n} < {MIN_N_KAPPA}: no se calcula kappa"
    cats = sorted({a for a, _ in pairs} | {b for _, b in pairs})
    po = sum(a == b for a, b in pairs) / n
    pe = sum(
        (sum(a == c for a, _ in pairs) / n) * (sum(b == c for _, b in pairs) / n) for c in cats
    )
    if pe >= 1:
        return None, "acuerdo esperado = 1 (una sola categoría): kappa indefinida"
    return round((po - pe) / (1 - pe), 4), None


def _binary(label: str) -> str:
    return "supported" if label == "supported" else "not_supported"


def compare_labels(
    reference: dict[str, str], evaluated: dict[str, str], name_ref: str, name_eval: str
) -> dict:
    """reference/evaluated = {claim_id: etiqueta}. Solo se comparan claim_ids presentes en
    ambos; los faltantes se informan."""
    common = sorted(set(reference) & set(evaluated))
    bad = [
        c for c in common if reference[c] not in LABELS or evaluated[c] not in JUDGE_FINAL_LABELS
    ]
    if bad:
        raise ValueError(f"etiquetas fuera del vocabulario en {bad}")
    pairs = [(reference[c], evaluated[c]) for c in common]
    n = len(pairs)
    cols = [*LABELS, *(lab for lab in JUDGE_FINAL_LABELS if lab not in LABELS)]
    matrix = {r: {c: 0 for c in cols} for r in LABELS}
    for a, b in pairs:
        matrix[a][b] += 1
    agree = sum(a == b for a, b in pairs)
    kappa, kappa_note = cohen_kappa(pairs)
    bpairs = [(_binary(a), _binary(b)) for a, b in pairs]
    bkappa, bkappa_note = cohen_kappa(bpairs)
    ref_not = [c for c in common if _binary(reference[c]) == "not_supported"]
    ref_sup = [c for c in common if reference[c] == "supported"]
    eval_sup_ref_not = [c for c in ref_not if evaluated[c] == "supported"]
    eval_not_ref_sup = [c for c in ref_sup if evaluated[c] != "supported"]
    return {
        "reference": name_ref,
        "evaluated": name_eval,
        "n_compared": n,
        "missing_in_evaluated": sorted(set(reference) - set(evaluated)),
        "missing_in_reference": sorted(set(evaluated) - set(reference)),
        "confusion_matrix": {
            "rows_reference": list(LABELS),
            "cols_evaluated": cols,
            "counts": matrix,
        },
        "agreement": {
            "value": round(agree / n, 4) if n else None,
            "k": agree,
            "n": n,
            "wilson95": wilson(agree, n),
        },
        "cohen_kappa": {"value": kappa, "note": kappa_note},
        "binary": {
            "agreement": round(sum(a == b for a, b in bpairs) / n, 4) if n else None,
            "cohen_kappa": {"value": bkappa, "note": bkappa_note},
        },
        # Error más peligroso: el evaluado da por respaldado algo que la referencia no.
        "evaluated_supported_reference_not": {
            "claim_ids": eval_sup_ref_not,
            "detail": [
                {"claim_id": c, "reference": reference[c], "evaluated": evaluated[c]}
                for c in eval_sup_ref_not
            ],
            "k": len(eval_sup_ref_not),
            "n_reference_not_supported": len(ref_not),
            "rate": round(len(eval_sup_ref_not) / len(ref_not), 4) if ref_not else None,
            "wilson95": wilson(len(eval_sup_ref_not), len(ref_not)),
        },
        "evaluated_not_reference_supported": {
            "claim_ids": eval_not_ref_sup,
            "k": len(eval_not_ref_sup),
            "n_reference_supported": len(ref_sup),
            "rate": round(len(eval_not_ref_sup) / len(ref_sup), 4) if ref_sup else None,
            "wilson95": wilson(len(eval_not_ref_sup), len(ref_sup)),
        },
        "warning": (
            f"Muestra pequeña (n={n}): los intervalos son amplios y el acuerdo observado no "
            "demuestra confiabilidad del evaluador."
            if n < SMALL_SAMPLE_N
            else "El acuerdo describe esta muestra; no garantiza el comportamiento en otras."
        ),
    }
