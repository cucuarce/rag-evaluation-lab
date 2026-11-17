"""Juez semántico (Etapa 3B) offline: config, solicitud estricta, independencia, errores de API,
caché, presupuesto, reanudación, selección congelada y comparación.

Todas las respuestas del "juez" son SIMULADAS (cliente guionado o transporte HTTP simulado).
"""

from __future__ import annotations

import ast
import json
from dataclasses import replace

import httpx
import pytest

from rag_lab.config import PROJECT_ROOT
from rag_lab.faithfulness.judge_client import JudgeGroqClient
from rag_lab.faithfulness.judge_compare import compare_run
from rag_lab.faithfulness.judge_config import load_judge_config, validate_judge_config
from rag_lab.faithfulness.judge_run import (
    REQUEST_CLAIM_ID,
    judge_messages,
    load_cases,
    run_judge,
)
from rag_lab.faithfulness.schema import JUDGE_SCHEMA, JUDGE_UNVERIFIABLE, read_jsonl
from rag_lab.faithfulness.smoke_selection import SMOKE_QUOTAS, select_smoke_cases
from rag_lab.generation.calls import ResponseCache
from rag_lab.generation.providers import GenerationResult, ProviderError
from rag_lab.hashing import sha256_file, sha256_json

PKG = PROJECT_ROOT / "src/rag_lab/faithfulness"
STAGE3 = PROJECT_ROOT / "data/stage3"
CFG_PATH = PROJECT_ROOT / "configs/judge_groq.toml"
FAKE_KEY = "gsk_test_not_a_real_key_0123456789"

ANSWERS = {a["answer_id"]: a for a in read_jsonl(STAGE3 / "answers.jsonl")}
CLAIMS = {c["claim_id"]: c for c in read_jsonl(STAGE3 / "claims_proposed.jsonl")}
PERTS = {p["pert_id"]: p for p in read_jsonl(STAGE3 / "perturbations.jsonl")}
HUMAN = {h["claim_id"]: h for h in read_jsonl(STAGE3 / "human_labels_round1.jsonl")}
REVIEWS = {r["pert_id"]: r for r in read_jsonl(STAGE3 / "perturbation_review.jsonl")}
# e01-c1: el fragmento S1 dice "Permite emitir hasta 500 facturas por mes".
QUOTE_E01 = "Permite emitir hasta 500 facturas por mes"


@pytest.fixture
def cfg():
    c = load_judge_config(CFG_PATH)
    return replace(c, limits=replace(c.limits, min_interval_s=0.0))


def _selection(*items):
    cases = [{"case_id": f"J{i:02d}", "type": t, "id": x} for i, (t, x) in enumerate(items, 1)]
    return {"cases": [c | {"stratum": "test"} for c in cases], "cases_sha256": sha256_json(cases)}


def _cases(*items):
    return load_cases(_selection(*items), CLAIMS, PERTS)


def _content(lc="supported", lx="supported", quote=QUOTE_E01, cite="S1"):
    ev = [{"cite_id": cite, "quote": quote}] if quote else []
    item = {
        "claim_id": REQUEST_CLAIM_ID,
        "label_cited": lc,
        "label_context": lx,
        "evidence": ev,
        "rationale": "simulado",
    }
    return json.dumps({"claims": [item]}, ensure_ascii=False)


class ScriptedJudge:
    """Cliente simulado: cada llamada consume el siguiente elemento (contenido o excepción)."""

    provider = "groq"
    model = "qwen/qwen3.8-27b"

    def __init__(self, *items):
        self.items = list(items)
        self.calls = 0
        self.seen: list[list[dict]] = []

    def generate(self, messages, schema):
        assert schema == JUDGE_SCHEMA
        self.calls += 1
        self.seen.append(messages)
        item = self.items.pop(0)
        if isinstance(item, Exception):
            raise item
        return GenerationResult(
            content=item,
            usage={"prompt_tokens": 1700, "completion_tokens": 300, "total_tokens": 2000},
            latency_s=0.5,
            model_returned=self.model,
            finish_reason="stop",
            request_id="req_x",
            ratelimit={"x-ratelimit-limit-tokens": "8000", "x-ratelimit-remaining-tokens": "7000"},
        )


def _run(cfg, client, tmp_path, cases, **kw):
    out = tmp_path / kw.pop("name", "run")
    run_judge(cases, ANSWERS, cfg, client, out, sleep=lambda s: None, **kw)
    preds = read_jsonl(out / "predictions.jsonl")
    manifest = json.loads((out / "judge_manifest.json").read_text(encoding="utf-8"))
    return preds, manifest, out


# --- Configuración y forma de la solicitud ------------------------------------------


def test_config_is_the_authorized_smoke(cfg):
    assert cfg.model.model == "qwen/qwen3.8-27b"
    assert cfg.limits.max_calls == 8 and cfg.limits.max_total_tokens == 25000
    assert cfg.limits.max_retries == 0 and cfg.limits.max_concurrency == 1
    assert cfg.request_params()["strict"] is True


@pytest.mark.parametrize(
    "change",
    [
        {"limits": {"max_retries": 5}},
        {"limits": {"max_concurrency": 2}},
        {"model": {"temperature": 0.9}},
        {"prompt_version": "judge-v2"},
    ],
)
def test_config_validation_rejects_unsafe_values(cfg, change):
    kw = {}
    for k, v in change.items():
        kw[k] = replace(getattr(cfg, k), **v) if isinstance(v, dict) else v
    with pytest.raises(ValueError):
        validate_judge_config(replace(cfg, **kw))


COMPLETION = {
    "id": "c1",
    "object": "chat.completion",
    "created": 0,
    "model": "qwen/qwen3.8-27b",
    "choices": [
        {"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": "{}"}}
    ],
    "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
}


def test_groq_request_uses_strict_json_schema(cfg):
    seen = {}

    def handler(request):
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json=COMPLETION)

    client = JudgeGroqClient(
        cfg, FAKE_KEY, http_client=httpx.Client(transport=httpx.MockTransport(handler))
    )
    client.generate([{"role": "user", "content": "x"}], JUDGE_SCHEMA)
    body = seen["body"]
    rf = body["response_format"]
    assert rf["type"] == "json_schema"
    assert rf["json_schema"]["strict"] is True
    assert rf["json_schema"]["name"] == "faithfulness_judgment"
    assert rf["json_schema"]["schema"] == JUDGE_SCHEMA
    assert body["model"] == "qwen/qwen3.8-27b" and body["temperature"] == 0.0
    assert body["seed"] == 7 and body["include_reasoning"] is False
    assert "reasoning_effort" not in body
    assert FAKE_KEY not in json.dumps(body)


# --- Independencia: el juez nunca ve etiquetas ---------------------------------------


JUDGE_SIDE = ("judge_run.py", "judge_client.py", "judge_config.py", "judge_prompt.py")
FORBIDDEN = (
    "human_labels",
    "perturbation_review",
    "expected_candidate",
    "stratum",
    "missing_premise",
    "smoke_selection",
    "judge_compare",
    "annotation",
    "labels.jsonl",
)


@pytest.mark.parametrize("name", JUDGE_SIDE)
def test_judge_side_modules_never_reference_reference_data(name):
    src = (PKG / name).read_text(encoding="utf-8")
    tree = ast.parse(src)
    code_strings = [
        n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str)
    ]
    idents = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    idents |= {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    mods = {n.module or "" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
    for word in FORBIDDEN:
        # Los docstrings pueden nombrar lo prohibido para explicarlo; el código no.
        assert not any(word in m for m in mods), (name, word)
        assert not any(word in i for i in idents), (name, word)
        assert not any(
            word in s
            for s in code_strings
            if not s.lstrip().startswith(("\n", '"')) and len(s) < 200
        ), (name, word)


def test_cases_carry_only_whitelisted_fields():
    sel = json.loads((STAGE3 / "judge_smoke_selection.json").read_text(encoding="utf-8"))
    for c in load_cases(sel, CLAIMS, PERTS):
        assert set(c) == {"case_id", "type", "source_id", "qid", "answer_id", "claim_text"}


def test_real_smoke_prompts_contain_no_reference_data():
    sel = json.loads((STAGE3 / "judge_smoke_selection.json").read_text(encoding="utf-8"))
    leaks = ["perturb", "stratum", "supported_", "pert_", "-p-", "h1", "esperad"]
    leaks += [c["id"] for c in sel["cases"]] + [c["stratum"] for c in sel["cases"]]
    leaks += [h["notes"] for h in HUMAN.values() if h["notes"]]
    leaks += [h["missing_premise"] for h in HUMAN.values() if h["missing_premise"]]
    for case in load_cases(sel, CLAIMS, PERTS):
        prompt = judge_messages(case, ANSWERS[case["answer_id"]], "2026-11-01")[0]["content"]
        found = [x for x in leaks if x and x in prompt]
        assert not found, (case["case_id"], found)
        # La afirmación que ve el juez es exactamente el texto del caso, con ID neutro.
        assert f"<<<AFIRMACION {REQUEST_CLAIM_ID} " in prompt
        assert case["claim_text"] in prompt
        if case["type"] == "perturbation":
            assert PERTS[case["source_id"]]["original_text"] not in prompt


def test_run_judge_signature_has_no_label_inputs():
    import inspect

    params = set(inspect.signature(run_judge).parameters)
    assert not params & {"human", "labels", "reviews", "references", "selection"}


# --- Verificación de citas en la corrida ---------------------------------------------


def test_valid_literal_quote_keeps_labels(cfg, tmp_path):
    preds, m, _ = _run(cfg, ScriptedJudge(_content()), tmp_path, _cases(("claim", "e01-c1")))
    p = preds[0]
    assert p["status"] == "ok"
    assert p["judge"]["label_cited"] == p["judge"]["label_context"] == "supported"
    assert p["citation_flags"] == {
        "unverifiable_cited": False,
        "unverifiable_context": False,
        "n_invalid_quotes": 0,
        "n_quotes": 1,
    }
    assert m["counts"]["http_requests"] == 1 and m["tokens_real"]["total_tokens"] == 2000


def test_fabricated_quote_is_judge_unverifiable_not_supported(cfg, tmp_path):
    bad = _content(quote="Permite emitir hasta 900 facturas por mes")
    preds, _, _ = _run(cfg, ScriptedJudge(bad), tmp_path, _cases(("claim", "e01-c1")))
    j = preds[0]["judge"]
    assert j["label_cited_raw"] == "supported"
    assert j["label_cited"] == j["label_context"] == JUDGE_UNVERIFIABLE
    assert preds[0]["citation_flags"]["unverifiable_cited"] is True


def test_unsupported_label_needs_no_quote(cfg, tmp_path):
    out = _content("unsupported", "unsupported", quote=None)
    preds, _, _ = _run(cfg, ScriptedJudge(out), tmp_path, _cases(("claim", "e01-c1")))
    assert preds[0]["judge"]["label_cited"] == "unsupported"


# --- Errores de API y de formato ------------------------------------------------------


THREE = (("claim", "e01-c1"), ("claim", "e02-c1"), ("claim", "e04-c1"))


@pytest.mark.parametrize(
    ("first", "status", "aborts"),
    [
        (
            ProviderError("rate_limit", "429", 429, transient=True, retry_after=5.0),
            "api_error",
            True,
        ),
        (ProviderError("bad_request", "strict no soportado", 400), "api_error", True),
        (ProviderError("not_found", "modelo", 404), "api_error", True),
        ("esto no es json", "format_error", True),
        (json.dumps({"claims": []}), "incomplete", True),
    ],
)
def test_quota_schema_and_format_problems_stop_the_run(cfg, tmp_path, first, status, aborts):
    client = ScriptedJudge(first, _content(), _content())
    preds, m, _ = _run(cfg, client, tmp_path, _cases(*THREE))
    assert preds[0]["status"] == status
    assert [p["status"] for p in preds[1:]] == ["not_run", "not_run"]
    assert client.calls == 1 and m["counts"]["http_requests"] == 1
    assert m["run_status"] == "aborted"


@pytest.mark.parametrize(
    "exc",
    [
        ProviderError("timeout", "timeout", transient=True),
        ProviderError("server_error", "503", 503, transient=True),
        ProviderError("connection", "refused", transient=True),
    ],
)
def test_transient_errors_are_not_retried_and_two_in_a_row_abort(cfg, tmp_path, exc):
    client = ScriptedJudge(exc, exc, _content())
    preds, m, _ = _run(cfg, client, tmp_path, _cases(*THREE))
    assert [p["status"] for p in preds] == ["api_error", "api_error", "not_run"]
    assert client.calls == 2  # max_retries = 0: una solicitud por caso
    assert "2 fallos consecutivos" in m["abort_reason"]


def test_single_transient_error_does_not_stop_the_run(cfg, tmp_path):
    client = ScriptedJudge(ProviderError("timeout", "t", transient=True), _content(), _content())
    preds, m, _ = _run(cfg, client, tmp_path, _cases(*THREE))
    assert [p["status"] for p in preds] == ["api_error", "ok", "ok"]
    assert m["run_status"] == "complete"


def test_truncated_output_is_reported_as_format_error(cfg, tmp_path):
    class Truncating(ScriptedJudge):
        def generate(self, messages, schema):
            r = super().generate(messages, schema)
            r.finish_reason = "length"
            return r

    preds, _, _ = _run(
        cfg, Truncating('{"claims": [{"claim_id": "A1"'), tmp_path, _cases(("claim", "e01-c1"))
    )
    assert preds[0]["status"] == "format_error"
    assert "truncada" in preds[0]["technical_error"]["message"]


def test_secret_is_redacted_from_errors(cfg, tmp_path):
    exc = ProviderError("bad_request", f"invalid key {FAKE_KEY}", 400)
    _, _, out = _run(
        cfg, ScriptedJudge(exc), tmp_path, _cases(("claim", "e01-c1")), secret=FAKE_KEY
    )
    for f in out.iterdir():
        assert FAKE_KEY not in f.read_text(encoding="utf-8")


# --- Presupuesto, caché y reanudación --------------------------------------------------


def test_call_budget_is_a_hard_cap(cfg, tmp_path):
    small = replace(cfg, limits=replace(cfg.limits, max_calls=2))
    client = ScriptedJudge(_content(), _content(), _content())
    preds, m, _ = _run(small, client, tmp_path, _cases(*THREE))
    assert [p["status"] for p in preds] == ["ok", "ok", "not_run"]
    assert client.calls == 2 and m["counts"]["http_requests"] == 2


def test_token_budget_blocks_calls_before_sending(cfg, tmp_path):
    tiny = replace(cfg, limits=replace(cfg.limits, max_total_tokens=1000))
    client = ScriptedJudge(_content())
    preds, _, _ = _run(tiny, client, tmp_path, _cases(("claim", "e01-c1")))
    assert preds[0]["status"] == "not_run" and client.calls == 0
    assert "presupuesto de tokens" in preds[0]["technical_error"]["message"]


def test_cache_hits_make_no_requests_and_predictions_are_not_overwritten(cfg, tmp_path):
    cache = ResponseCache(tmp_path / "cache")
    cases = _cases(("claim", "e01-c1"))
    p1, _, out = _run(cfg, ScriptedJudge(_content()), tmp_path, cases, cache=cache)
    with pytest.raises(FileExistsError):
        run_judge(cases, ANSWERS, cfg, ScriptedJudge(), out, cache=cache, sleep=lambda s: None)
    client = ScriptedJudge()
    p2, m2, _ = _run(cfg, client, tmp_path, cases, cache=cache, name="run", force=True)
    assert client.calls == 0 and m2["counts"]["cache_hits"] == 1
    assert p2[0]["judge"] == p1[0]["judge"]


def test_resume_after_abort_reuses_cache(cfg, tmp_path):
    cache = ResponseCache(tmp_path / "cache")
    cases = _cases(*THREE)
    first = ScriptedJudge(_content(), ProviderError("bad_request", "x", 400))
    p1, _, _ = _run(cfg, first, tmp_path, cases, cache=cache, name="r1")
    assert [p["status"] for p in p1] == ["ok", "api_error", "not_run"]
    second = ScriptedJudge(_content(), _content())  # solo los dos que faltan
    p2, m2, _ = _run(cfg, second, tmp_path, cases, cache=cache, name="r2")
    assert [p["status"] for p in p2] == ["ok", "ok", "ok"]
    assert second.calls == 2 and m2["counts"]["cache_hits"] == 1


def test_errors_are_not_cached(cfg, tmp_path):
    cache = ResponseCache(tmp_path / "cache")
    cases = _cases(("claim", "e01-c1"))
    _run(
        cfg,
        ScriptedJudge(ProviderError("timeout", "t", transient=True)),
        tmp_path,
        cases,
        cache=cache,
        name="a",
    )
    client = ScriptedJudge(_content())
    _run(cfg, client, tmp_path, cases, cache=cache, name="b")
    assert client.calls == 1


# --- Selección congelada ----------------------------------------------------------------


def test_frozen_selection_is_reproducible_and_balanced():
    frozen = json.loads((STAGE3 / "judge_smoke_selection.json").read_text(encoding="utf-8"))
    sel = select_smoke_cases(HUMAN, REVIEWS, list(PERTS.values()))
    assert sel["cases"] == frozen["cases"] and sel["cases_sha256"] == frozen["cases_sha256"]
    assert sha256_json(frozen["cases"]) == frozen["cases_sha256"]
    cases = frozen["cases"]
    assert len(cases) == sum(q for _, q in SMOKE_QUOTAS) == 8
    kinds = [PERTS[c["id"]]["kind"] for c in cases if c["type"] == "perturbation"]
    assert kinds.count("number") >= 2 and kinds.count("negation") + kinds.count("unit") >= 2
    for c in cases:
        if c["type"] == "perturbation":
            assert REVIEWS[c["id"]]["human_confirms_expected"] == "si"
            assert HUMAN[PERTS[c["id"]]["source_claim_id"]]["label_cited"] == "supported"
        else:
            h = HUMAN[c["id"]]
            want = c["stratum"].removeprefix("orig_")
            assert h["label_cited"] == want and h["split_decision"] == "aceptar"


# --- Comparación posterior ----------------------------------------------------------------


def test_compare_classifies_outcomes_and_never_touches_predictions(cfg, tmp_path):
    sel = _selection(
        ("claim", "e01-c1"),  # humano: supported / supported
        ("claim", "e05-c3"),  # humano: partially_supported / supported
        ("perturbation", "e01-c1-p-number"),  # confirmada: unsupported / unsupported
        ("claim", "e02-c1"),
    )
    for c in sel["cases"]:
        c["stratum"] = "test"
    cases = load_cases(sel, CLAIMS, PERTS)
    client = ScriptedJudge(
        _content(),  # J01 acuerdo
        _content(quote="texto inventado que no está"),  # J02 judge_unverifiable
        _content(),  # J03 juez supported, humano unsupported (cita válida pero de otro caso)
        ProviderError("timeout", "t", transient=True),  # J04 fallo técnico
    )
    _, _, out = _run(cfg, client, tmp_path, cases)
    before = sha256_file(out / "predictions.jsonl")
    rep = compare_run(out, sel, HUMAN, REVIEWS, PERTS)
    assert sha256_file(out / "predictions.jsonl") == before == rep["predictions_sha256"]
    by = {r["case_id"]: r for r in rep["per_case"]}
    assert by["J01"]["label_cited"]["outcome"] == "agree"
    assert by["J02"]["label_cited"]["outcome"] == "citation_error"
    # La perturbación usa la misma respuesta que e01-c1: la cita es literal y válida, pero la
    # etiqueta "supported" es errónea. Una cita válida no hace correcta la etiqueta.
    assert by["J03"]["label_cited"]["outcome"] == "semantic_error"
    assert by["J04"]["label_cited"]["outcome"] == "technical_failure"
    cited = rep["per_field"]["label_cited"]
    assert cited["evaluated_supported_reference_not"]["claim_ids"] == ["J03"]
    assert cited["n_compared"] == 3  # el fallo técnico no entra en la matriz
    assert cited["cohen_kappa"]["value"] is None  # n < 10


def test_compare_rejects_tampered_predictions(cfg, tmp_path):
    sel = _selection(("claim", "e01-c1"))
    sel["cases"][0]["stratum"] = "test"
    _, _, out = _run(cfg, ScriptedJudge(_content()), tmp_path, load_cases(sel, CLAIMS, PERTS))
    p = out / "predictions.jsonl"
    p.write_text(p.read_text(encoding="utf-8").replace("supported", "unsupported"), "utf-8")
    with pytest.raises(ValueError, match="sha256"):
        compare_run(out, sel, HUMAN, REVIEWS, PERTS)
