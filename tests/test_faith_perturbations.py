"""Perturbaciones: cada una modifica el hecho evaluado y no se trata como verdad de referencia."""

from __future__ import annotations

from rag_lab.config import PROJECT_ROOT
from rag_lab.faithfulness.perturbations import (
    SELECTION_QUOTAS,
    perturb_negation,
    perturb_number,
    perturb_unit,
    select_perturbations,
    usable_perturbations,
)
from rag_lab.faithfulness.schema import read_jsonl

STAGE3 = PROJECT_ROOT / "data/stage3"
CHUNK = (
    "Una suscripción mensual nueva puede recibir un reembolso total si el cliente lo "
    "solicita dentro de los 30 días corridos posteriores al primer cobro."
)


def _claim(text, cid="c1"):
    return {"claim_id": cid, "answer_id": "a", "qid": "q", "text": text}


def test_number_changes_to_value_absent_from_context():
    p = perturb_number(_claim("El plazo es de 30 días corridos."), [CHUNK], [CHUNK, "90 días"])
    assert p["change"] == ["30", "60"]  # 60 no está en el contexto; 90 sí lo estaría con n*3
    assert p["perturbed_text"] == "El plazo es de 60 días corridos."
    assert p["reference_status"] == "candidate" and p["needs_human_confirmation"]


def test_number_absent_from_cited_is_not_perturbed():
    # "8" (derivado de la pregunta) no está en lo citado: no hay hecho citado que cambiar.
    assert perturb_number(_claim("8 usuarios exceden lo incluido."), [CHUNK], [CHUNK]) is None


def test_number_lower_bound_of_range_is_skipped():
    chunk = "se acredita en un plazo de 5 a 10 días hábiles."
    p = perturb_number(_claim("Se acredita en 5 a 10 días hábiles."), [chunk], [chunk])
    assert p["change"][0] == "10" and "5 a 20" in p["perturbed_text"]


def test_negation_removal_checks_it_is_written_in_cited():
    chunk = "la diferencia de precio no se devuelve al medio de pago"
    p = perturb_negation(_claim("La diferencia no se devuelve al medio de pago."), [chunk])
    assert p["perturbed_text"] == "La diferencia se devuelve al medio de pago."
    assert p["reference_status"] == "candidate"
    q = perturb_negation(_claim("El plan Pro no incluye SSO."), ["SSO en Pro Plus y Enterprise."])
    assert q["reference_status"] == "requires_review"


def test_negation_add_handles_clitics_and_hasta():
    p = perturb_negation(_claim("Kestrel lo reintenta tres veces."), ["Kestrel lo reintenta"])
    assert p["perturbed_text"] == "Kestrel no lo reintenta tres veces."
    q = perturb_negation(_claim("Una cuenta puede emitir hasta 500."), ["Permite emitir"])
    assert q["reference_status"] == "requires_review"
    assert any("hasta" in r for r in q["reasons"])


def test_unit_swap_requires_original_unit_in_cited():
    p = perturb_unit(_claim("Son 30 días corridos."), [CHUNK], [CHUNK])
    assert p["change"] == ["30 días corridos", "30 días hábiles"]
    assert p["reference_status"] == "candidate"
    bad = perturb_unit(_claim("Pagará USD 96 por mes."), [CHUNK], [CHUNK])
    assert bad["reference_status"] == "invalid"  # "96 por mes" no está en lo citado


def test_usable_requires_human_supported_unedited_and_confirmed():
    perts = [
        {
            "pert_id": "p1",
            "source_claim_id": "c1",
            "reference_status": "candidate",
            "human_confirms_expected": "si",
        },
        {
            "pert_id": "p2",
            "source_claim_id": "c2",
            "reference_status": "candidate",
            "human_confirms_expected": "si",
        },
        {"pert_id": "p3", "source_claim_id": "c1", "reference_status": "candidate"},
        {
            "pert_id": "p4",
            "source_claim_id": "c3",
            "reference_status": "invalid",
            "human_confirms_expected": "si",
        },
        {
            "pert_id": "p5",
            "source_claim_id": "c4",
            "reference_status": "candidate",
            "human_confirms_expected": "si",
        },
    ]
    human = {
        "c1": {"split_decision": "aceptar", "label_cited": "supported"},
        "c2": {"split_decision": "aceptar", "label_cited": "partially_supported"},
        "c3": {"split_decision": "aceptar", "label_cited": "supported"},
        "c4": {"split_decision": "editar", "label_cited": "supported"},
    }
    assert [p["pert_id"] for p in usable_perturbations(perts, human)] == ["p1"]


def test_stage3_perturbations_file_is_consistent():
    perts = read_jsonl(STAGE3 / "perturbations.jsonl")
    claims = {c["claim_id"]: c for c in read_jsonl(STAGE3 / "claims_proposed.jsonl")}
    selected = [p for p in perts if p["selected"]]
    assert len(selected) == sum(q for _, q in SELECTION_QUOTAS)
    for p in perts:
        assert p["original_text"] == claims[p["source_claim_id"]]["text"]
        assert p["needs_human_confirmation"] is True
        if p["reference_status"] != "invalid":
            assert p["checks"]["text_changed"] and p["perturbed_text"] != p["original_text"]
    for p in selected:
        assert p["reference_status"] != "invalid"
    kinds = {p["kind"] for p in selected}
    assert kinds == {"number", "negation", "unit", "version"}


def test_selection_is_deterministic():
    perts = read_jsonl(STAGE3 / "perturbations.jsonl")
    a = [p["pert_id"] for p in select_perturbations([dict(p) for p in perts])]
    b = [p["pert_id"] for p in select_perturbations([dict(p) for p in perts])]
    assert a == b == [p["pert_id"] for p in perts if p["selected"]]
