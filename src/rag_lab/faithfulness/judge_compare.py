"""Comparación juez vs referencia humana, DESPUÉS de guardar las predicciones.

Referencia por caso:
- afirmación original: etiquetas humanas de la ronda 1 (`label_cited`, `label_context`);
- perturbación: la expectativa (`unsupported` / `unsupported`) solo si una persona la
  confirmó (`human_confirms_expected = si`); si no, el caso queda sin referencia.

Resultado por caso y por etiqueta:
- technical_failure: el juez no produjo una etiqueta (api_error, not_run, formato, faltante);
- citation_error: el juez declaró respaldo sin una cita literal válida (judge_unverifiable);
- semantic_error: etiqueta verificada distinta de la referencia;
- agree.

Las predicciones no se modifican: se verifica su sha256 contra el manifiesto antes y después.
"""

from __future__ import annotations

import json
from pathlib import Path

from rag_lab.faithfulness.agreement import compare_labels
from rag_lab.faithfulness.schema import JUDGE_UNVERIFIABLE, read_jsonl
from rag_lab.hashing import sha256_file

FIELDS = ("label_cited", "label_context")


def references(
    selection: dict, human: dict[str, dict], reviews: dict[str, dict], perts: dict[str, dict]
) -> dict[str, dict]:
    out = {}
    for c in selection["cases"]:
        if c["type"] == "claim":
            h = human[c["id"]]
            if h["split_decision"] != "aceptar":
                continue
            out[c["case_id"]] = {f: h[f] for f in FIELDS} | {"source": "human_label_round1"}
        else:
            r = reviews.get(c["id"])
            if r and r["human_confirms_expected"] == "si":
                exp = perts[c["id"]]["expected_candidate"]
                out[c["case_id"]] = {f: exp[f] for f in FIELDS} | {
                    "source": "perturbation_confirmed"
                }
    return out


def _outcome(pred: dict, field: str, ref: str | None) -> str | None:
    if ref is None:
        return None
    if pred["status"] != "ok":
        return "technical_failure"
    final = pred["judge"][field]
    if final == JUDGE_UNVERIFIABLE:
        return "citation_error"
    return "agree" if final == ref else "semantic_error"


def compare_run(
    run_dir: Path,
    selection: dict,
    human: dict[str, dict],
    reviews: dict[str, dict],
    perts: dict[str, dict],
) -> dict:
    pred_path = run_dir / "predictions.jsonl"
    manifest = json.loads((run_dir / "judge_manifest.json").read_text(encoding="utf-8"))
    sha_before = sha256_file(pred_path)
    if sha_before != manifest["predictions_sha256"]:
        raise ValueError("predictions.jsonl no coincide con el sha256 del manifiesto")
    preds = {p["case_id"]: p for p in read_jsonl(pred_path)}
    if [c["case_id"] for c in selection["cases"]] != list(preds):
        raise ValueError("las predicciones no corresponden a la selección")
    refs = references(selection, human, reviews, perts)
    strata = {c["case_id"]: c["stratum"] for c in selection["cases"]}

    rows = []
    for cid, p in preds.items():
        ref = refs.get(cid)
        row = {
            "case_id": cid,
            "type": p["type"],
            "source_id": p["source_id"],
            "qid": p["qid"],
            "stratum": strata[cid],
            "claim_text": p["claim_text"],
            "status": p["status"],
            "technical_error": p["technical_error"],
            "reference_source": ref["source"] if ref else None,
        }
        for f in FIELDS:
            j = p["judge"] or {}
            row[f] = {
                "reference": ref[f] if ref else None,
                "judge_raw": j.get(f"{f}_raw"),
                "judge_final": j.get(f),
                "outcome": _outcome(p, f, ref[f] if ref else None),
            }
        row["citation_flags"] = p["citation_flags"]
        row["rationale"] = (p["judge"] or {}).get("rationale")
        rows.append(row)

    ok = {cid for cid, p in preds.items() if p["status"] == "ok"}
    per_field = {}
    for f in FIELDS:
        ref_map = {cid: r[f] for cid, r in refs.items()}
        ev_map = {cid: preds[cid]["judge"][f] for cid in ok}
        cmp = compare_labels(ref_map, ev_map, "humano", "juez")
        outcomes: dict[str, int] = {}
        for r in rows:
            o = r[f]["outcome"]
            if o:
                outcomes[o] = outcomes.get(o, 0) + 1
        cmp["outcomes"] = outcomes
        per_field[f] = cmp

    if sha256_file(pred_path) != sha_before:
        raise AssertionError("las predicciones cambiaron durante la comparación")
    return {
        "run_dir": run_dir.as_posix(),
        "predictions_sha256": sha_before,
        "n_cases": len(rows),
        "n_with_reference": len(refs),
        "n_technical_ok": len(ok),
        "per_case": rows,
        "per_field": per_field,
        "unverifiable_cases": [
            r["case_id"]
            for r in rows
            if r["citation_flags"]
            and (
                r["citation_flags"]["unverifiable_cited"]
                or r["citation_flags"]["unverifiable_context"]
            )
        ],
        "invalid_quote_cases": [
            r["case_id"]
            for r in rows
            if r["citation_flags"] and r["citation_flags"]["n_invalid_quotes"]
        ],
        "note": (
            "Smoke descriptivo: n muy chico y casos elegidos a mano por estrato. No estima la "
            "confiabilidad del juez ni tasas de error generalizables."
        ),
    }
