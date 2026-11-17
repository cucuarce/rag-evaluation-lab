"""Selección reproducible de casos para el smoke del juez (Etapa 3B).

Usa las etiquetas humanas y las revisiones de perturbaciones SOLO para elegir y equilibrar
casos. La selección congelada que consume el juez lleva tipo e id por caso; el estrato queda
registrado para el análisis, pero `judge_run` no lo lee y nunca entra al prompt.

Regla: por estrato, candidatos ordenados por sha256("<seed>:<id>"); se prefiere no repetir
qid entre casos y, si un estrato no se completa, se permite repetir.
"""

from __future__ import annotations

import hashlib

from rag_lab.faithfulness.perturbations import usable_perturbations
from rag_lab.hashing import sha256_json

SMOKE_SEED = "stage3b-smoke-v1"
# El estrato más escaso primero, para que no lo agoten los demás al evitar qids repetidos.
SMOKE_QUOTAS = (
    ("orig_partially_supported", 2),
    ("pert_number", 2),
    ("pert_negation", 1),
    ("pert_unit", 1),
    ("orig_supported", 2),
)


def _rank(item_id: str, seed: str) -> str:
    return hashlib.sha256(f"{seed}:{item_id}".encode()).hexdigest()


def _pools(human: dict[str, dict], reviews: dict[str, dict], perts: list[dict]) -> dict:
    unedited = {
        cid: h
        for cid, h in human.items()
        if h["split_decision"] == "aceptar" and not h.get("claim_text_final")
    }
    merged = [
        p | {"human_confirms_expected": reviews[p["pert_id"]]["human_confirms_expected"]}
        for p in perts
        if p["pert_id"] in reviews
    ]
    usable = usable_perturbations(merged, human)
    pools: dict[str, list[tuple[str, str, str]]] = {k: [] for k, _ in SMOKE_QUOTAS}
    for cid, h in unedited.items():
        if h["label_cited"] == "supported" and h["label_context"] == "supported":
            pools["orig_supported"].append(("claim", cid, h["qid"]))
        elif h["label_cited"] == "partially_supported":
            pools["orig_partially_supported"].append(("claim", cid, h["qid"]))
    for p in usable:
        key = f"pert_{p['kind']}"
        if key in pools:
            pools[key].append(("perturbation", p["pert_id"], p["qid"]))
    return pools


def select_smoke_cases(
    human: dict[str, dict],
    reviews: dict[str, dict],
    perts: list[dict],
    seed: str = SMOKE_SEED,
) -> dict:
    pools = _pools(human, reviews, perts)
    used_qids: set[str] = set()
    chosen: list[dict] = []
    for stratum, quota in SMOKE_QUOTAS:
        ranked = sorted(pools[stratum], key=lambda t: _rank(t[1], seed))
        picked: list[tuple[str, str, str]] = []
        for allow_repeat in (False, True):
            for t in ranked:
                if len(picked) == quota:
                    break
                taken = used_qids | {p[2] for p in picked}
                if t in picked or (not allow_repeat and t[2] in taken):
                    continue
                picked.append(t)
        if len(picked) < quota:
            raise ValueError(f"estrato {stratum}: {len(picked)} candidatos < cupo {quota}")
        for kind, sid, qid in picked:
            used_qids.add(qid)
            chosen.append({"type": kind, "id": sid, "qid": qid, "stratum": stratum})
    cases = [{"case_id": f"J{i:02d}"} | c for i, c in enumerate(chosen, start=1)]
    return {
        "purpose": "smoke del juez semántico (Etapa 3B): selección congelada antes de ejecutar",
        "seed": seed,
        "quotas": [list(q) for q in SMOKE_QUOTAS],
        "pool_sizes": {k: len(v) for k, v in pools.items()},
        "cases": cases,
        "cases_sha256": sha256_json(cases),
    }
