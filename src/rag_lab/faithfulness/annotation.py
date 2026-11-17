"""Exportación de la planilla de anotación humana e importación de etiquetas.

La planilla es ciega: no muestra la corrida (A/B), métricas de la Etapa 2, la respuesta de
referencia, los hechos requeridos/prohibidos, el motivo de selección ni salidas de un juez.
Muestra pregunta, respuesta, afirmación propuesta, citas y fragmentos citados; el paquete
Markdown agrega todos los fragmentos del contexto con su vigencia.

Formato: CSV separado por ";" en UTF-8 con BOM (se abre bien en Excel en español). La
importación acepta ";" o "," y rechaza el archivo entero ante cualquier valor inválido.
Las etiquetas humanas se guardan en un archivo propio, separado de cualquier salida del juez.
"""

from __future__ import annotations

import csv
import io
import random
from pathlib import Path

from rag_lab.faithfulness.schema import (
    SUBTYPES,
    SUPPORTED_LIKE,
    ContractError,
    validate_human_label,
)
from rag_lab.hashing import sha256_bytes
from rag_lab.text import strip_accents

ORDER_SEED = 3
READONLY_COLS = (
    "item",
    "claim_id",
    "qid",
    "question",
    "temporal_scope",
    "answer",
    "claim_text",
    "proposed_subtypes",
    "cited_ids",
    "cited_fragments",
)
FILL_COLS = (
    "split_decision",
    "claim_text_final",
    "label_cited",
    "label_context",
    "support_cite_ids",
    "version_issue",
    "subtypes_final",
    "missing_premise",
    "notes",
    "annotator",
)
PERT_READONLY = (
    "pert_id",
    "source_claim_id",
    "kind",
    "original_text",
    "perturbed_text",
    "change",
    "reference_status",
    "reasons",
    "expected_label_cited",
    "expected_label_context",
)
PERT_FILL = ("human_confirms_expected", "notes", "annotator")


def _ordered_groups(claims: list[dict]) -> list[tuple[str, list[dict]]]:
    groups: dict[str, list[dict]] = {}
    for c in claims:
        groups.setdefault(c["answer_id"], []).append(c)
    keys = sorted(groups)
    random.Random(ORDER_SEED).shuffle(keys)
    return [(k, groups[k]) for k in keys]


def _csv_text(header: tuple, rows: list[dict]) -> str:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=header, delimiter=";", lineterminator="\n")
    w.writeheader()
    for r in rows:
        w.writerow(r)
    return buf.getvalue()


def build_annotation_sheet(claims: list[dict], answers: dict[str, dict]) -> str:
    rows = []
    item = 0
    for aid, group in _ordered_groups(claims):
        ans = answers[aid]
        cited = [c for c in ans["context"] if c["cite_id"] in ans["cited_cite_ids"]]
        frag = "\n\n".join(f"[{c['cite_id']}] ({c['vigencia']}) {c['text']}" for c in cited)
        for c in group:
            item += 1
            rows.append(
                {
                    "item": item,
                    "claim_id": c["claim_id"],
                    "qid": c["qid"],
                    "question": ans["question"],
                    "temporal_scope": ans["temporal_scope"]["kind"],
                    "answer": ans["answer"],
                    "claim_text": c["text"],
                    "proposed_subtypes": ",".join(c["subtypes"]),
                    "cited_ids": ",".join(ans["cited_cite_ids"]),
                    "cited_fragments": frag,
                }
                | dict.fromkeys(FILL_COLS, "")
            )
    return _csv_text(READONLY_COLS + FILL_COLS, rows)


def build_annotation_packet(claims: list[dict], answers: dict[str, dict]) -> str:
    out = [
        "# Paquete de anotación — Etapa 3A",
        "",
        "Generado por `rag-lab faith-prepare`. No editar: se regenera. Las etiquetas van en "
        "`annotation_sheet.csv`. Guía: `docs/annotation_guide.md`.",
        "",
        "No se muestran la corrida (A/B), métricas, respuestas de referencia ni hechos "
        "esperados: se evalúa solo si los fragmentos respaldan cada afirmación.",
        "",
    ]
    for gi, (aid, group) in enumerate(_ordered_groups(claims), start=1):
        ans = answers[aid]
        out += [
            f"## Grupo {gi} — {ans['qid']} (answer_id `{aid}`)",
            "",
            f"**Pregunta:** {ans['question']}",
            "",
            f"**Alcance temporal (regla de la Etapa 2):** `{ans['temporal_scope']['kind']}`",
            "",
            f"**Respuesta:** {ans['answer']}",
            "",
            f"**Citó:** {', '.join(ans['cited_cite_ids'])}",
            "",
            "**Afirmaciones a etiquetar:**",
            "",
        ]
        for c in group:
            out.append(f"- `{c['claim_id']}` — {c['text']}")
        out += ["", "**Fragmentos del contexto (en el orden entregado al generador):**", ""]
        for ch in ans["context"]:
            mark = " — **CITADO**" if ch["cite_id"] in ans["cited_cite_ids"] else ""
            out += [
                f"**[{ch['cite_id']}]** `{ch['doc_id']}` v{ch['version']} — {ch['vigencia']}{mark}",
                "",
                *[f"> {line}" if line else ">" for line in ch["text"].splitlines()],
                "",
            ]
        out.append("---")
        out.append("")
    return "\n".join(out)


def build_perturbation_sheet(perts: list[dict]) -> str:
    rows = [
        {
            "pert_id": p["pert_id"],
            "source_claim_id": p["source_claim_id"],
            "kind": p["kind"],
            "original_text": p["original_text"],
            "perturbed_text": p["perturbed_text"],
            "change": " -> ".join(p["change"]),
            "reference_status": p["reference_status"],
            "reasons": "; ".join(p["reasons"]),
            "expected_label_cited": p["expected_candidate"]["label_cited"],
            "expected_label_context": p["expected_candidate"]["label_context"] or "a decidir",
        }
        | dict.fromkeys(PERT_FILL, "")
        for p in perts
        if p["reference_status"] != "invalid"
    ]
    return _csv_text(PERT_READONLY + PERT_FILL, rows)


def write_if_unchanged(path: Path, text: str, force: bool) -> str:
    """Escribe salvo que el archivo exista con otro contenido (p. ej. ya anotado)."""
    if path.exists():
        current = path.read_text(encoding="utf-8-sig")
        if current == text:
            return "sin cambios"
        if not force:
            raise FileExistsError(
                f"{path} ya existe con otro contenido (¿anotado?). No se sobrescribe; usá "
                "--force solo si querés descartarlo."
            )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8-sig", newline="\n")
    return "escrito"


def read_sheet(path: Path) -> tuple[list[dict], str]:
    raw = path.read_bytes()
    text = raw.decode("utf-8-sig")
    first = text.split("\n", 1)[0]
    delim = ";" if first.count(";") >= first.count(",") else ","
    rows = list(csv.DictReader(io.StringIO(text), delimiter=delim))
    return rows, sha256_bytes(raw)


def _norm_choice(v: str | None) -> str:
    return strip_accents((v or "").strip()).lower()


def _split_list(v: str | None) -> list[str]:
    return [x.strip() for x in (v or "").replace(";", ",").split(",") if x.strip()]


def import_human_labels(
    sheet: Path, claims: dict[str, dict], answers: dict[str, dict], round_: int
) -> dict:
    rows, sheet_sha = read_sheet(sheet)
    missing_cols = [c for c in ("claim_id", *FILL_COLS) if rows and c not in rows[0]]
    if missing_cols:
        raise ContractError(f"faltan columnas en la planilla: {missing_cols}")
    out, errors, pending = [], [], []
    seen = set()
    for r in rows:
        cid = (r.get("claim_id") or "").strip()
        if cid not in claims:
            errors.append(f"{cid or '(vacío)'}: claim_id desconocido")
            continue
        if cid in seen:
            errors.append(f"{cid}: fila duplicada")
            continue
        seen.add(cid)
        if not any((r.get(k) or "").strip() for k in FILL_COLS):
            pending.append(cid)
            continue
        claim = claims[cid]
        ans = answers[claim["answer_id"]]
        row = {
            "claim_id": cid,
            "answer_id": claim["answer_id"],
            "qid": claim["qid"],
            "runs": claim["runs"],
            "claim_text_proposed": claim["text"],
            "split_decision": _norm_choice(r.get("split_decision")),
            "claim_text_final": (r.get("claim_text_final") or "").strip(),
            "label_cited": _norm_choice(r.get("label_cited")),
            "label_context": _norm_choice(r.get("label_context")),
            "support_cite_ids": [s.upper() for s in _split_list(r.get("support_cite_ids"))],
            "version_issue": _norm_choice(r.get("version_issue")),
            "subtypes_final": [s.lower() for s in _split_list(r.get("subtypes_final"))]
            or claim["subtypes"],
            "missing_premise": (r.get("missing_premise") or "").strip(),
            "notes": (r.get("notes") or "").strip(),
            "annotator": (r.get("annotator") or "").strip(),
            "round": round_,
            "source": "human",
            "sheet_sha256": sheet_sha,
        }
        errs = validate_human_label(row)
        if not row["annotator"]:
            errs.append("annotator vacío")
        bad_sub = [s for s in row["subtypes_final"] if s not in SUBTYPES]
        if bad_sub:
            errs.append(f"subtypes_final inválidos: {bad_sub}")
        if row["split_decision"] != "rechazar":
            ctx_ids = {c["cite_id"] for c in ans["context"]}
            unknown = [s for s in row["support_cite_ids"] if s not in ctx_ids]
            if unknown:
                errs.append(f"support_cite_ids fuera del contexto: {unknown}")
            if row["label_cited"] in SUPPORTED_LIKE and not (
                set(row["support_cite_ids"]) & set(ans["cited_cite_ids"])
            ):
                errs.append("label_cited supported/partially_supported sin fragmento citado")
        errors += [f"{cid}: {e}" for e in errs]
        out.append(row)
    if errors:
        raise ContractError("planilla inválida, no se importó nada:\n  " + "\n  ".join(errors))
    return {"labels": out, "pending": pending, "sheet_sha256": sheet_sha}


def import_perturbation_review(sheet: Path, perts: dict[str, dict]) -> dict:
    rows, sheet_sha = read_sheet(sheet)
    out, errors, pending = [], [], []
    for r in rows:
        pid = (r.get("pert_id") or "").strip()
        if pid not in perts:
            errors.append(f"{pid or '(vacío)'}: pert_id desconocido")
            continue
        v = _norm_choice(r.get("human_confirms_expected"))
        if not v:
            pending.append(pid)
            continue
        if v not in ("si", "no"):
            errors.append(f"{pid}: human_confirms_expected debe ser si/no")
            continue
        if not (r.get("annotator") or "").strip():
            errors.append(f"{pid}: annotator vacío")
            continue
        out.append(
            {
                "pert_id": pid,
                "human_confirms_expected": v,
                "notes": (r.get("notes") or "").strip(),
                "annotator": r["annotator"].strip(),
                "sheet_sha256": sheet_sha,
            }
        )
    if errors:
        raise ContractError("planilla inválida, no se importó nada:\n  " + "\n  ".join(errors))
    return {"reviews": out, "pending": pending, "sheet_sha256": sheet_sha}
