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

from rag_lab.faithfulness.agreement import compare_labels, wilson
from rag_lab.faithfulness.schema import JUDGE_UNVERIFIABLE, read_jsonl
from rag_lab.hashing import sha256_file

FIELDS = ("label_cited", "label_context")
GROUPS = {"claim": "originales", "perturbation": "perturbaciones_sinteticas"}
PERT_SUBTYPE = {"number": "numeric", "negation": "negation", "unit": "unit"}
# Campos que deben coincidir exactamente al reutilizar una predicción de otra corrida.
REUSE_FIELDS = (
    "type",
    "source_id",
    "claim_text",
    "prompt_sha256",
    "cache_key",
    "status",
    "judge",
    "citation_flags",
)


def references(
    selection: dict, human: dict[str, dict], reviews: dict[str, dict], perts: dict[str, dict]
) -> dict[str, dict]:
    out: dict[str, dict] = {}
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


def _subtypes(row: dict, human: dict[str, dict], perts: dict[str, dict]) -> list[str]:
    """Subtipos para el análisis: los humanos (`subtypes_final`) en originales; en
    perturbaciones, el tipo de perturbación (sintético)."""
    if row["type"] == "claim":
        return list(human[row["source_id"]].get("subtypes_final") or [])
    return [PERT_SUBTYPE.get(perts[row["source_id"]]["kind"], perts[row["source_id"]]["kind"])]


def _group_stats(rows: list[dict], field: str) -> dict:
    with_ref = [r for r in rows if r[field]["reference"] is not None]
    agree = sum(r[field]["outcome"] == "agree" for r in with_ref)
    n = len(with_ref)
    not_sup = [r for r in with_ref if r[field]["reference"] != "supported"]
    over = [r["case_id"] for r in not_sup if r[field]["judge_final"] == "supported"]
    return {
        "n": n,
        "agree": agree,
        "agreement": round(agree / n, 4) if n else None,
        "wilson95": wilson(agree, n),
        "n_reference_not_supported": len(not_sup),
        "judge_supported_reference_not": over,
        "errors": [r["case_id"] for r in with_ref if r[field]["outcome"] != "agree"],
    }


def reuse_check(run_dir: Path, source_dir: Path) -> dict:
    """Verifica que los casos tomados de otra corrida (misma solicitud exacta, vía caché)
    reproducen su predicción campo por campo, sin solicitudes HTTP."""
    src = {p["case_id"]: p for p in read_jsonl(source_dir / "predictions.jsonl")}
    cur = {p["case_id"]: p for p in read_jsonl(run_dir / "predictions.jsonl")}
    rows = []
    for cid, a in src.items():
        b = cur.get(cid)
        diffs = ["missing"] if b is None else [k for k in REUSE_FIELDS if a.get(k) != b.get(k)]
        if b is not None:
            la, lb = a.get("llm") or {}, b.get("llm") or {}
            for k in ("raw_content", "request_id", "usage", "model_returned"):
                if la.get(k) != lb.get(k):
                    diffs.append(f"llm.{k}")
            if lb.get("http_requests"):
                diffs.append("llm.http_requests>0")
        rows.append({"case_id": cid, "identical": not diffs, "diffs": diffs})
    return {
        "source_run": source_dir.as_posix(),
        "n": len(rows),
        "all_identical": all(r["identical"] for r in rows),
        "cases": rows,
    }


def compare_run(
    run_dir: Path,
    selection: dict,
    human: dict[str, dict],
    reviews: dict[str, dict],
    perts: dict[str, dict],
    reuse_from: Path | None = None,
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
    origins = {c["case_id"]: c.get("origin") for c in selection["cases"]}

    rows = []
    for cid, p in preds.items():
        ref = refs.get(cid)
        row = {
            "case_id": cid,
            "type": p["type"],
            "source_id": p["source_id"],
            "qid": p["qid"],
            "stratum": strata[cid],
            "origin": origins[cid],
            "synthetic_control": p["type"] == "perturbation",
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
        row["subtypes"] = _subtypes(row, human, perts)
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

    per_group = {}
    for kind, name in GROUPS.items():
        g_ids = {r["case_id"] for r in rows if r["type"] == kind}
        per_group[name] = {
            f: compare_labels(
                {cid: r[f] for cid, r in refs.items() if cid in g_ids},
                {cid: preds[cid]["judge"][f] for cid in ok if cid in g_ids},
                "humano",
                "juez",
            )
            for f in FIELDS
        }
    subtypes = sorted({s for r in rows for s in r["subtypes"]})
    by_subtype = {
        f"{GROUPS[kind]}:{st}": {
            f: _group_stats([r for r in rows if r["type"] == kind and st in r["subtypes"]], f)
            for f in FIELDS
        }
        for kind in GROUPS
        for st in subtypes
        if any(r["type"] == kind and st in r["subtypes"] for r in rows)
    }
    reuse = reuse_check(run_dir, reuse_from) if reuse_from else None

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
        "per_group": per_group,
        "by_subtype": by_subtype,
        "reuse_check": reuse,
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
            "Descriptivo: n chico, casos no aleatorios (afirmaciones de una sola corrida de "
            "generación) y perturbaciones sintéticas derivadas de esas mismas afirmaciones. No "
            "estima la confiabilidad general del juez ni tasas de error generalizables. Una cita "
            "literal válida no demuestra faithfulness."
        ),
    }


def pilot_stability(run_dir: Path, pilot_dirs: list[Path]) -> dict:
    """Compara las etiquetas de una corrida con las de corridas piloto de OTRA configuración,
    caso por caso (mismo case_id y misma afirmación). Es un control de estabilidad: nunca
    mezcla predicciones ni entra en los agregados. Solo usa casos `ok` en ambas corridas y no
    copia mensajes de error (pueden traer identificadores del proveedor)."""
    cur = {p["case_id"]: p for p in read_jsonl(run_dir / "predictions.jsonl")}
    cfg_cur = json.loads((run_dir / "judge_manifest.json").read_text(encoding="utf-8"))
    rows, pilots, seen = [], [], {}
    duplicates = []
    for d in pilot_dirs:
        man = json.loads((d / "judge_manifest.json").read_text(encoding="utf-8"))
        if sha256_file(d / "predictions.jsonl") != man["predictions_sha256"]:
            raise ValueError(f"{d}: predictions.jsonl no coincide con su manifiesto")
        if man["judge_config_hash"] == cfg_cur["judge_config_hash"]:
            raise ValueError(f"{d}: el piloto debe ser de otra configuración")
        pilots.append(
            {
                "run": d.name,
                "predictions_sha256": man["predictions_sha256"],
                "max_completion_tokens": man["request_params"]["max_completion_tokens"],
            }
        )
        for p in read_jsonl(d / "predictions.jsonl"):
            if p["status"] != "ok":
                continue
            if p["case_id"] in seen:
                # El mismo caso en dos pilotos (p. ej. reutilizado por caché): se cuenta una vez
                # y se exige que sea la misma respuesta.
                if seen[p["case_id"]] != p["cache_key"]:
                    raise ValueError(f"{p['case_id']}: pilotos con respuestas distintas")
                duplicates.append({"case_id": p["case_id"], "pilot_run": d.name})
                continue
            seen[p["case_id"]] = p["cache_key"]
            b = cur.get(p["case_id"])
            if b is None or b["source_id"] != p["source_id"]:
                raise ValueError(f"{p['case_id']}: el piloto no corresponde a la selección")
            if b["claim_text"] != p["claim_text"] or b["prompt_sha256"] != p["prompt_sha256"]:
                raise ValueError(f"{p['case_id']}: la afirmación o el prompt difieren")
            row = {"case_id": p["case_id"], "source_id": p["source_id"], "pilot_run": d.name}
            row["current_status"] = b["status"]
            for f in FIELDS:
                pv = p["judge"][f]
                cv = (b["judge"] or {}).get(f)
                row[f] = {"pilot": pv, "current": cv, "same": pv == cv}
            rows.append(row)
    comparable = [r for r in rows if r["current_status"] == "ok"]
    return {
        "note": "control de estabilidad entre configuraciones; no se mezcla en los agregados",
        "pilots": pilots,
        "n_pilot_ok": len(rows),
        "duplicates_skipped": duplicates,
        "n_comparable": len(comparable),
        "same": {f: sum(r[f]["same"] for r in comparable) for f in FIELDS},
        "changed": [r["case_id"] for r in comparable if not all(r[f]["same"] for f in FIELDS)],
        "cases": rows,
    }
