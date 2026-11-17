"""Validador de la salida del juez (no confía en el juez).

1. Formato: JSON que cumpla `JUDGE_SCHEMA` (claves exactas, tipos, etiquetas del enum).
   Un error de formato invalida la respuesta entera (no se repara).
2. Cobertura: una entrada por claim_id pedido; faltantes y extras se registran.
3. Evidencia: cada `quote` debe existir LITERALMENTE (substring exacto) en el texto del
   fragmento `cite_id` declarado, que debe pertenecer al contexto; mínimo `MIN_QUOTE_CHARS`
   caracteres no blancos para evitar citas triviales ("30").
4. Etiqueta final: si el juez dice supported/partially_supported y no hay ninguna cita
   válida en el conjunto que corresponde (fragmentos citados para `label_cited`, cualquier
   fragmento del contexto para `label_context`), la etiqueta final es `judge_unverifiable`
   y cuenta como NO respaldada. Las etiquetas unsupported/insufficient_context no requieren
   cita.

Una cita válida es condición necesaria, no suficiente: el verificador nunca sube una
etiqueta a supported porque la cita exista, ni comprueba que la cita respalde la afirmación.
Eso lo mide el acuerdo con la anotación humana.
"""

from __future__ import annotations

import json

from rag_lab.faithfulness.schema import JUDGE_UNVERIFIABLE, LABELS, SUPPORTED_LIKE

MIN_QUOTE_CHARS = 8
_ITEM_KEYS = {"claim_id", "label_cited", "label_context", "evidence", "rationale"}


def _format_error(raw: str) -> tuple[list[dict] | None, str | None]:
    try:
        obj = json.loads(raw)
    except (json.JSONDecodeError, TypeError) as exc:
        return None, f"JSON inválido: {exc}"
    if not isinstance(obj, dict) or set(obj) != {"claims"}:
        return None, "el objeto raíz debe tener solo la clave 'claims'"
    items = obj["claims"]
    if not isinstance(items, list):
        return None, "'claims' debe ser una lista"
    for i, it in enumerate(items):
        if not isinstance(it, dict) or set(it) != _ITEM_KEYS:
            return None, f"claims[{i}]: claves distintas de {sorted(_ITEM_KEYS)}"
        if not isinstance(it["claim_id"], str) or not isinstance(it["rationale"], str):
            return None, f"claims[{i}]: claim_id/rationale deben ser texto"
        for key in ("label_cited", "label_context"):
            if it[key] not in LABELS:
                return None, f"claims[{i}].{key} fuera del enum: {it[key]!r}"
        ev = it["evidence"]
        if not isinstance(ev, list):
            return None, f"claims[{i}].evidence debe ser una lista"
        for j, e in enumerate(ev):
            if (
                not isinstance(e, dict)
                or set(e) != {"cite_id", "quote"}
                or not all(isinstance(v, str) for v in e.values())
            ):
                return None, f"claims[{i}].evidence[{j}] inválida"
    return items, None


def check_quote(quote: str, cite_id: str, context_text: dict[str, str]) -> dict:
    in_context = cite_id in context_text
    long_enough = len("".join(quote.split())) >= MIN_QUOTE_CHARS
    literal = in_context and bool(quote) and quote in context_text[cite_id]
    return {
        "cite_id": cite_id,
        "quote": quote,
        "cite_in_context": in_context,
        "long_enough": long_enough,
        "literal_match": literal,
        "valid": in_context and long_enough and literal,
    }


def _final(raw_label: str, valid_cites: set[str], allowed: set[str]) -> str:
    if raw_label in SUPPORTED_LIKE and not (valid_cites & allowed):
        return JUDGE_UNVERIFIABLE
    return raw_label


def verify_judgment(
    raw: str,
    claim_ids: list[str],
    context_text: dict[str, str],
    cited_cite_ids: list[str],
) -> dict:
    """raw = contenido devuelto por el juez; context_text = {cite_id: texto del fragmento}."""
    items, err = _format_error(raw)
    if err:
        return {"format_ok": False, "format_error": err, "claims": [], "issues": [err]}
    issues = []
    seen: dict[str, dict] = {}
    for it in items:
        if it["claim_id"] in seen:
            issues.append(f"claim_id duplicado: {it['claim_id']} (se usa el primero)")
            continue
        seen[it["claim_id"]] = it
    extra = sorted(set(seen) - set(claim_ids))
    if extra:
        issues.append(f"claim_ids no pedidos (ignorados): {extra}")
    out = []
    for cid in claim_ids:
        it = seen.get(cid)
        if it is None:
            issues.append(f"falta el claim_id {cid}")
            out.append({"claim_id": cid, "missing": True})
            continue
        checks = [check_quote(e["quote"], e["cite_id"], context_text) for e in it["evidence"]]
        valid = {c["cite_id"] for c in checks if c["valid"]}
        out.append(
            {
                "claim_id": cid,
                "missing": False,
                "judge_label_cited": it["label_cited"],
                "judge_label_context": it["label_context"],
                "label_cited": _final(it["label_cited"], valid, set(cited_cite_ids)),
                "label_context": _final(it["label_context"], valid, set(context_text)),
                "evidence_checks": checks,
                "n_invalid_quotes": sum(not c["valid"] for c in checks),
                "rationale": it["rationale"],
            }
        )
    return {"format_ok": True, "format_error": None, "claims": out, "issues": issues}
