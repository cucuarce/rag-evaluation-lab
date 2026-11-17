"""Perturbaciones controladas de afirmaciones (controles negativos para el juez).

Tipos (como máximo una perturbación de cada tipo por afirmación, determinística):
- number:   cambia un número que aparece en los fragmentos citados por otro que no aparece
            en ningún fragmento del contexto.
- negation: quita una negación ("no se devuelve" -> "se devuelve") o la agrega delante del
            primer verbo de una lista cerrada.
- unit:     cambia la unidad ("días hábiles" <-> "días corridos", "minutos" -> "horas", ...).
- version:  reemplaza un número por el valor que tiene la otra versión del mismo documento
            (v3 <-> v2) en la misma sección.

Cada perturbación registra comprobaciones automáticas de que realmente modifica el hecho
evaluado (el texto cambió; el valor original aparece en lo citado; el valor nuevo no aparece
en el contexto). Aun si pasan, el resultado es solo una CANDIDATA a etiqueta de referencia:
- `candidate`: comprobaciones automáticas OK; requiere confirmación humana.
- `requires_review`: la expectativa depende de juicio (negaciones no explícitas, versiones,
  valor nuevo presente en el contexto).
- `invalid`: no cambia el hecho evaluado (texto igual, valor original ausente de lo citado).
Una perturbación solo se usa como referencia si además la afirmación original fue etiquetada
`supported` por una persona, no fue editada y la persona confirmó la expectativa
(`usable_perturbations`).
"""

from __future__ import annotations

import re

from rag_lab.evaluation.lexical_v2 import unicode_clean
from rag_lab.text import strip_accents

_NUM = re.compile(r"(?<![\w.,])(\d+(?:[.,]\d+)?)(?![\w]|[.,]\d)")
_RANGE_LOWER = re.compile(r"\s+a\s+\d")
CLITICS = ("lo", "la", "los", "las", "le", "les", "me", "te", "nos")
NEGATABLE_VERBS = (
    "se conservan",
    "se acredita",
    "se aplica",
    "se bloquea",
    "se actualiza",
    "se suspende",
    "se devuelve",
    "puede",
    "pueden",
    "incluye",
    "acepta",
    "debe",
    "cuesta",
    "permite",
    "dura",
    "reintenta",
    "devuelve",
    "tiene",
    "sirve",
)
UNIT_SWAPS = (
    ("días hábiles", "días corridos"),
    ("días corridos", "días hábiles"),
    ("minutos", "horas"),
    ("horas", "minutos"),
    ("por mes", "por año"),
    ("al mes", "al año"),
    ("meses", "años"),
    ("años", "meses"),
    ("días", "meses"),
)


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", strip_accents(unicode_clean(text)).lower())


def _has_number(value: str, text: str) -> bool:
    pat = rf"(?<![\w.,]){re.escape(value)}(?![\w]|[.,]\d)"
    return re.search(pat, unicode_clean(text)) is not None


def _has_phrase(phrase: str, text: str) -> bool:
    return re.search(rf"(?<!\w){re.escape(_norm(phrase))}(?!\w)", _norm(text)) is not None


def _alternatives(value: str) -> list[str]:
    if "," in value or ("." in value and len(value.split(".")[-1]) != 3):
        v = float(value.replace(",", "."))
        alts = [v - 1, v - 2, v + 3]
        return [f"{a:.1f}".replace(".", ",") for a in alts]
    n = int(value.replace(".", ""))
    return [str(a) for a in ((n * 2, n * 3, n + 7, n + 13) if n else (1, 2, 3))]


def _replace_first(text: str, old: str, new: str) -> str:
    pat = rf"(?<![\w.,]){re.escape(old)}(?![\w]|[.,]\d)"
    return re.sub(pat, new, text, count=1)


def _base(claim: dict, kind: str) -> dict:
    return {
        "pert_id": f"{claim['claim_id']}-p-{kind}",
        "source_claim_id": claim["claim_id"],
        "answer_id": claim["answer_id"],
        "qid": claim["qid"],
        "kind": kind,
        "original_text": claim["text"],
        "needs_human_confirmation": True,
    }


def _finish(rec: dict, checks: dict, review_reasons: list[str], expected: dict) -> dict:
    rec["checks"] = checks
    invalid = [k for k in ("text_changed", "original_in_cited") if checks.get(k) is False]
    if invalid:
        rec["reference_status"] = "invalid"
        rec["reasons"] = [f"falla: {k}" for k in invalid]
    elif review_reasons:
        rec["reference_status"] = "requires_review"
        rec["reasons"] = review_reasons
    else:
        rec["reference_status"] = "candidate"
        rec["reasons"] = []
    rec["expected_candidate"] = expected
    return rec


def perturb_number(claim: dict, cited: list[str], context: list[str]) -> dict | None:
    for m in _NUM.finditer(claim["text"]):
        value = m.group(1)
        # Límite inferior de un rango ("5 a 10"): cambiarlo puede invertir el rango.
        if _RANGE_LOWER.match(claim["text"], m.end()):
            continue
        if not any(_has_number(value, t) for t in cited):
            continue
        for alt in _alternatives(value):
            if not any(_has_number(alt, t) for t in context):
                break
        new = _replace_first(claim["text"], value, alt)
        rec = _base(claim, "number") | {"perturbed_text": new, "change": [value, alt]}
        checks = {
            "text_changed": new != claim["text"],
            "original_in_cited": True,
            "perturbed_in_cited": any(_has_number(alt, t) for t in cited),
            "perturbed_in_context": any(_has_number(alt, t) for t in context),
        }
        reasons = (
            ["el valor nuevo aparece en el contexto"] if checks["perturbed_in_context"] else []
        )
        exp = {"label_cited": "unsupported", "label_context": "unsupported"}
        return _finish(rec, checks, reasons, exp)
    return None


def perturb_negation(claim: dict, cited: list[str]) -> dict | None:
    text = claim["text"]
    m = re.search(r"(?<!\w)no (\w+)", text)
    if m:
        new = text[: m.start()] + text[m.start() + 3 :]
        verb = m.group(1)
        # ¿La negación está escrita en lo citado? (prefijo de 4 letras: tiene/tienen)
        stem = _norm(verb)[:4]
        explicit = any(re.search(rf"\bno {re.escape(stem)}", _norm(t)) for t in cited)
        rec = _base(claim, "negation") | {
            "direction": "remove",
            "perturbed_text": new,
            "change": ["no " + verb, verb],
        }
        checks = {
            "text_changed": new != text,
            "original_in_cited": None,
            "negation_explicit_in_cited": explicit,
        }
        reasons = [] if explicit else ["la negación original no está escrita en lo citado"]
        exp = {"label_cited": "unsupported", "label_context": "unsupported"}
        return _finish(rec, checks, reasons, exp)
    best = None
    for verb in NEGATABLE_VERBS:
        vm = re.search(rf"(?<!\w){re.escape(verb)}(?!\w)", text)
        if vm and (best is None or vm.start() < best.start()):
            best = vm
    if best is None:
        return None
    start = best.start()
    prev = re.search(r"(\w+) $", text[:start])
    if prev and prev.group(1).lower() in CLITICS:  # "lo reintenta" -> "no lo reintenta"
        start = prev.start(1)
    new = text[:start] + "no " + text[start:]
    affirmed = any(_has_phrase(best.group(0), t) for t in cited)
    changed = text[start : best.end()]
    rec = _base(claim, "negation") | {
        "direction": "add",
        "perturbed_text": new,
        "change": [changed, "no " + changed],
    }
    checks = {
        "text_changed": new != text,
        "original_in_cited": None,
        "verb_affirmed_in_cited": affirmed,
    }
    reasons = [] if affirmed else ["el verbo afirmado no aparece literal en lo citado"]
    if re.search(r"(?<!\w)hasta(?!\w)", text[best.end() :]):
        reasons.append("negación delante de 'hasta': el alcance de la negación es ambiguo")
    exp = {"label_cited": "unsupported", "label_context": "unsupported"}
    return _finish(rec, checks, reasons, exp)


def perturb_unit(claim: dict, cited: list[str], context: list[str]) -> dict | None:
    text = claim["text"]
    for old, new_unit in UNIT_SWAPS:
        pat = rf"(?<!\w){re.escape(old)}(?!\w)"
        if old == "días":
            pat += r"(?! (hábiles|corridos))"
        m = re.search(pat, text)
        if not m:
            continue
        new = text[: m.start()] + new_unit + text[m.end() :]
        num = re.search(r"(\d+(?:[.,]\d+)?)\s*$", text[: m.start()])
        if num:
            orig_phrase = f"{num.group(1)} {old}"
            new_phrase = f"{num.group(1)} {new_unit}"
        else:
            orig_phrase, new_phrase = old, new_unit
        checks = {
            "text_changed": new != text,
            "original_in_cited": any(_has_phrase(orig_phrase, t) for t in cited),
            "perturbed_in_context": any(_has_phrase(new_phrase, t) for t in context),
        }
        rec = _base(claim, "unit") | {"perturbed_text": new, "change": [orig_phrase, new_phrase]}
        reasons = (
            ["la frase nueva aparece en el contexto"] if checks["perturbed_in_context"] else []
        )
        exp = {"label_cited": "unsupported", "label_context": "unsupported"}
        return _finish(rec, checks, reasons, exp)
    return None


def perturb_version(
    claim: dict,
    cited_chunks: list[dict],
    context: list[str],
    counterpart_chunks: dict[str, list[dict]],
) -> dict | None:
    """counterpart_chunks = {chunk_id citado: [chunks de la otra versión, misma sección]}."""
    for ch in cited_chunks:
        for other in counterpart_chunks.get(ch["chunk_id"], []):
            a = [m.group(1) for m in _NUM.finditer(unicode_clean(ch["text"]))]
            b = [m.group(1) for m in _NUM.finditer(unicode_clean(other["text"]))]
            if len(a) != len(b):
                continue
            for va, vb in zip(a, b, strict=True):
                if va == vb or not _has_number(va, claim["text"]):
                    continue
                new = _replace_first(claim["text"], va, vb)
                rec = _base(claim, "version") | {
                    "perturbed_text": new,
                    "change": [va, vb],
                    "counterpart_chunk_id": other["chunk_id"],
                    "counterpart_status": other["status"],
                }
                checks = {
                    "text_changed": new != claim["text"],
                    "original_in_cited": True,
                    "perturbed_in_context": any(_has_number(vb, t) for t in context),
                }
                reasons = [
                    "versión: la etiqueta esperada en contexto completo depende del alcance "
                    "temporal y de si la otra versión está en el contexto"
                ]
                exp = {"label_cited": "unsupported", "label_context": None}
                return _finish(rec, checks, reasons, exp)
    return None


def counterpart_map(cited_chunks: list[dict], docs: dict, all_chunks: list[dict]) -> dict:
    """Para cada chunk citado, los chunks de la otra versión del documento con la misma
    sección (sucesor si el citado es deprecated; predecesores si es vigente)."""
    out: dict[str, list[dict]] = {}
    for ch in cited_chunks:
        doc = docs[ch["doc_id"]]
        others = {d.doc_id for d in docs.values() if d.superseded_by == doc.doc_id}
        if doc.superseded_by:
            others.add(doc.superseded_by)
        out[ch["chunk_id"]] = [
            {
                "chunk_id": c["chunk_id"],
                "text": c["text"],
                "status": docs[c["doc_id"]].status,
            }
            for c in all_chunks
            if c["doc_id"] in others and c["section"] == ch["section"]
        ]
    return out


def perturb_claim(claim: dict, answer: dict, counterparts: dict) -> list[dict]:
    cited = [c for c in answer["context"] if c["cite_id"] in answer["cited_cite_ids"]]
    cited_t = [c["text"] for c in cited]
    ctx_t = [c["text"] for c in answer["context"]]
    out = [
        perturb_number(claim, cited_t, ctx_t),
        perturb_negation(claim, cited_t),
        perturb_unit(claim, cited_t, ctx_t),
        perturb_version(claim, cited, ctx_t, counterparts),
    ]
    return [p for p in out if p is not None]


def usable_perturbations(perts: list[dict], human: dict[str, dict]) -> list[dict]:
    """Perturbaciones utilizables como referencia: candidata o revisada, confirmada por una
    persona, y afirmación original aceptada sin editar y etiquetada supported."""
    out = []
    for p in perts:
        h = human.get(p["source_claim_id"])
        if (
            p["reference_status"] != "invalid"
            and p.get("human_confirms_expected") == "si"
            and h is not None
            and h.get("split_decision") == "aceptar"
            and h.get("label_cited") == "supported"
        ):
            out.append(p)
    return out


# Cupos de la selección pequeña que va a revisión humana (el resto queda registrado).
SELECTION_QUOTAS = (
    (("version", None), 2),
    (("negation", "remove"), 5),
    (("number", None), 6),
    (("unit", None), 4),
    (("negation", "add"), 4),
)


def select_perturbations(perts: list[dict]) -> list[dict]:
    """Selección determinística y chica: por tipo en el orden de `SELECTION_QUOTAS`,
    excluye `invalid`, prefiere `candidate` y afirmaciones todavía no usadas, en el orden de
    las afirmaciones. Marca `selected` en cada perturbación (también en las no elegidas)."""
    used: set[str] = set()
    chosen: set[str] = set()
    for (kind, direction), quota in SELECTION_QUOTAS:
        pool = [
            p
            for p in perts
            if p["kind"] == kind
            and (direction is None or p.get("direction") == direction)
            and p["reference_status"] != "invalid"
        ]
        ranked = sorted(
            range(len(pool)),
            key=lambda i: (
                pool[i]["source_claim_id"] in used,
                pool[i]["reference_status"] != "candidate",
                i,
            ),
        )
        for i in ranked[:quota]:
            chosen.add(pool[i]["pert_id"])
            used.add(pool[i]["source_claim_id"])
    for p in perts:
        p["selected"] = p["pert_id"] in chosen
    return [p for p in perts if p["selected"]]
