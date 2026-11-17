"""Orquestación offline de la Etapa 3A: respuestas únicas, perturbaciones y planillas."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from rag_lab.chunking import chunk_corpus
from rag_lab.config import PROJECT_ROOT, resolve_path
from rag_lab.corpus import load_corpus
from rag_lab.faithfulness.annotation import (
    build_annotation_packet,
    build_annotation_sheet,
    build_perturbation_sheet,
    write_if_unchanged,
)
from rag_lab.faithfulness.answers import collect_unique_answers
from rag_lab.faithfulness.judge_prompt import (
    JUDGE_PROMPT_VERSION,
    build_judge_messages,
    template_sha256,
)
from rag_lab.faithfulness.perturbations import (
    counterpart_map,
    perturb_claim,
    select_perturbations,
)
from rag_lab.faithfulness.schema import JUDGE_SCHEMA, read_jsonl, validate_claims, write_jsonl
from rag_lab.generation.calls import estimate_tokens
from rag_lab.hashing import sha256_file, sha256_json

STAGE3 = PROJECT_ROOT / "data" / "stage3"
DEFAULT_GEN_DIRS = [
    PROJECT_ROOT / "runs/eval/A_dense_k5/gen/groq_gpt-oss-120b",
    PROJECT_ROOT / "runs/eval/B_hybrid_k5/gen/groq_gpt-oss-120b",
]
# Tope de salida supuesto para el futuro juez (razonamiento + JSON de ~2 afirmaciones).
JUDGE_MAX_COMPLETION_TOKENS = 1024


def prepare(
    gen_dirs: list[Path] = DEFAULT_GEN_DIRS, out_dir: Path = STAGE3, force: bool = False
) -> dict:
    answers, provenance = collect_unique_answers(gen_dirs)
    by_id = {a["answer_id"]: a for a in answers}
    write_jsonl(out_dir / "answers.jsonl", answers)

    claims_path = out_dir / "claims_proposed.jsonl"
    claims = read_jsonl(claims_path)
    validate_claims(claims, by_id)

    gm = json.loads((gen_dirs[0] / "gen_manifest.json").read_text(encoding="utf-8"))
    reference_date = gm["generation_config"]["reference_date"]
    rm = json.loads((resolve_path(gm["retrieval_run"]) / "manifest.json").read_text("utf-8"))
    docs = load_corpus(resolve_path(rm["config"]["corpus_dir"]))
    all_chunks = [c.to_dict() for c in chunk_corpus(docs, rm["config"]["chunking"]["max_chars"])]

    perts = []
    for c in claims:
        ans = by_id[c["answer_id"]]
        cited = [x for x in ans["context"] if x["cite_id"] in ans["cited_cite_ids"]]
        perts += perturb_claim(c, ans, counterpart_map(cited, docs, all_chunks))
    selected = select_perturbations(perts)
    write_jsonl(out_dir / "perturbations.jsonl", perts)

    ann = out_dir / "annotation"
    status = {
        "annotation_sheet.csv": write_if_unchanged(
            ann / "annotation_sheet.csv", build_annotation_sheet(claims, by_id), force
        ),
        "perturbation_review.csv": write_if_unchanged(
            ann / "perturbation_review.csv", build_perturbation_sheet(selected), force
        ),
    }
    (ann / "annotation_packet.md").write_text(
        build_annotation_packet(claims, by_id), encoding="utf-8", newline="\n"
    )

    # Dimensionamiento del futuro juez (sin llamar a nada): una solicitud por respuesta.
    groups: dict[str, list[tuple[str, str]]] = {}
    for c in claims:
        groups.setdefault(c["answer_id"], []).append((c["claim_id"], c["text"]))
    estimates = [
        estimate_tokens(
            build_judge_messages(by_id[aid], cl, reference_date), JUDGE_MAX_COMPLETION_TOKENS
        )
        for aid, cl in groups.items()
    ]

    texts = Counter(a["answer"] for a in answers)
    manifest = {
        "stage": "3A",
        "sources": provenance["sources"],
        "reference_date": reference_date,
        "answers": {
            "unique_answers": len(answers),
            "distinct_answer_texts": len(texts),
            "occurrences": sum(len(a["occurrences"]) for a in answers),
            "shared_by_A_and_B": [a["qid"] for a in answers if len(a["occurrences"]) > 1],
            "answers_sha256": sha256_file(out_dir / "answers.jsonl"),
        },
        "claims": {
            "path": claims_path.relative_to(PROJECT_ROOT).as_posix()
            if claims_path.is_relative_to(PROJECT_ROOT)
            else str(claims_path),
            "sha256": sha256_file(claims_path),
            "n_claims": len(claims),
            "n_answers_with_claims": len(groups),
            "qids": sorted({c["qid"] for c in claims}),
            "by_subtype": dict(Counter(s for c in claims for s in c["subtypes"])),
            "by_run": dict(Counter("+".join(sorted(c["runs"])) for c in claims)),
        },
        "perturbations": {
            "n": len(perts),
            "by_kind": dict(Counter(p["kind"] for p in perts)),
            "by_reference_status": dict(Counter(p["reference_status"] for p in perts)),
            "selected_for_review": len(selected),
            "selected_by_kind": dict(
                Counter(f"{p['kind']}/{p.get('direction', '-')}" for p in selected)
            ),
            "selected_by_reference_status": dict(Counter(p["reference_status"] for p in selected)),
            "note": "Candidatas sintéticas: no son etiquetas de referencia hasta que una "
            "persona confirme la expectativa y la afirmación original sea supported.",
        },
        "judge_contract": {
            "prompt_version": JUDGE_PROMPT_VERSION,
            "template_sha256": template_sha256(),
            "schema_sha256": sha256_json(JUDGE_SCHEMA),
            "dry_run_requests": len(estimates),
            "dry_run_estimated_tokens_total": sum(estimates),
            "estimate_rule": "ceil(caracteres/2,5) + "
            f"{JUDGE_MAX_COMPLETION_TOKENS} de salida por solicitud (sobreestima)",
            "note": "Estimación sin llamadas. Ningún juez real fue ejecutado en la Etapa 3A.",
        },
        "annotation_files": status,
    }
    (out_dir / "stage3a_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return manifest
