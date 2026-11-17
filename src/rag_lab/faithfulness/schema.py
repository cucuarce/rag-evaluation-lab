"""Contratos de la Etapa 3A: afirmaciones, etiquetas humanas y salida del juez."""

from __future__ import annotations

import json
from pathlib import Path

LABELS = ("supported", "partially_supported", "unsupported", "insufficient_context")
# Etiqueta que solo produce el verificador (nunca el juez ni la persona): el juez dijo
# supported/partially_supported pero ninguna cita textual suya existe en los fragmentos.
JUDGE_UNVERIFIABLE = "judge_unverifiable"
JUDGE_FINAL_LABELS = (*LABELS, JUDGE_UNVERIFIABLE)
SUPPORTED_LIKE = ("supported", "partially_supported")

SUBTYPES = ("extractive", "numeric", "negation", "derived", "version", "multi_hop")

SPLIT_DECISIONS = ("aceptar", "editar", "rechazar")
YES_NO = ("si", "no")

CLAIM_FIELDS = (
    "claim_id",
    "answer_id",
    "qid",
    "runs",
    "text",
    "answer_span",
    "subtypes",
    "proposed_by",
    "status",
)


class ContractError(ValueError):
    pass


def read_jsonl(path: Path) -> list[dict]:
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")


def validate_claims(claims: list[dict], answers: dict[str, dict]) -> None:
    """Afirmaciones propuestas: IDs únicos, respuesta existente, fragmento literal de la
    respuesta, subtipos válidos y trazabilidad a las corridas A/B."""
    seen = set()
    for c in claims:
        cid = c.get("claim_id")
        missing = [k for k in CLAIM_FIELDS if k not in c]
        if missing:
            raise ContractError(f"{cid}: faltan campos {missing}")
        if cid in seen:
            raise ContractError(f"claim_id duplicado: {cid}")
        seen.add(cid)
        ans = answers.get(c["answer_id"])
        if ans is None:
            raise ContractError(f"{cid}: answer_id inexistente {c['answer_id']}")
        if ans["qid"] != c["qid"]:
            raise ContractError(f"{cid}: qid {c['qid']} != {ans['qid']}")
        if sorted(c["runs"]) != sorted(o["run"] for o in ans["occurrences"]):
            raise ContractError(f"{cid}: runs no coinciden con la respuesta")
        if c["answer_span"] not in ans["answer"]:
            raise ContractError(f"{cid}: answer_span no es un fragmento literal de la respuesta")
        if not c["text"].strip():
            raise ContractError(f"{cid}: texto vacío")
        bad = [s for s in c["subtypes"] if s not in SUBTYPES]
        if bad or not c["subtypes"]:
            raise ContractError(f"{cid}: subtipos inválidos {c['subtypes']}")
        if c["status"] != "proposed_unreviewed":
            raise ContractError(f"{cid}: status debe ser 'proposed_unreviewed' hasta la revisión")


def validate_human_label(row: dict) -> list[str]:
    """Errores de una fila de etiqueta humana (vacío = válida)."""
    errs = []
    decision = row.get("split_decision")
    if decision not in SPLIT_DECISIONS:
        errs.append(f"split_decision inválido: {decision!r}")
        return errs
    if decision == "rechazar":
        return errs
    if decision == "editar" and not (row.get("claim_text_final") or "").strip():
        errs.append("split_decision=editar requiere claim_text_final")
    for key in ("label_cited", "label_context"):
        if row.get(key) not in LABELS:
            errs.append(f"{key} inválido: {row.get(key)!r}")
    if row.get("version_issue") not in YES_NO:
        errs.append(f"version_issue inválido: {row.get('version_issue')!r}")
    # Coherencia: lo citado es un subconjunto del contexto, así que no puede estar mejor
    # respaldado por lo citado que por el contexto completo.
    rank = {"supported": 3, "partially_supported": 2, "unsupported": 1, "insufficient_context": 1}
    lc, lx = row.get("label_cited"), row.get("label_context")
    if lc in rank and lx in rank and rank[lc] > rank[lx]:
        errs.append(f"label_cited={lc} es más fuerte que label_context={lx}")
    if lc in SUPPORTED_LIKE and not row.get("support_cite_ids"):
        errs.append("label_cited supported/partially_supported requiere support_cite_ids")
    return errs


# Esquema de salida estructurada del futuro juez (Groq json_schema, strict=true).
# Una llamada por respuesta: el juez etiqueta todas sus afirmaciones.
JUDGE_SCHEMA: dict = {
    "type": "object",
    "additionalProperties": False,
    "required": ["claims"],
    "properties": {
        "claims": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["claim_id", "label_cited", "label_context", "evidence", "rationale"],
                "properties": {
                    "claim_id": {"type": "string"},
                    "label_cited": {"type": "string", "enum": list(LABELS)},
                    "label_context": {"type": "string", "enum": list(LABELS)},
                    "evidence": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "required": ["cite_id", "quote"],
                            "properties": {
                                "cite_id": {"type": "string"},
                                "quote": {"type": "string"},
                            },
                        },
                    },
                    "rationale": {"type": "string"},
                },
            },
        }
    },
}
