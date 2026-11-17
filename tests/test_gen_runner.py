"""Gate, abstención, caché, presupuesto, abortos y reproducibilidad offline."""

from __future__ import annotations

import json
from dataclasses import replace

import pytest

from rag_lab.generation.calls import Budget, BudgetExceeded, Pacer, ResponseCache
from rag_lab.generation.gate import gate_score, load_gate
from rag_lab.generation.providers import FakeGenerator, ProviderError
from rag_lab.generation.runner import run_generation
from tests.gen_helpers import (
    ANSWER_S1,
    ScriptedGenerator,
    fake_cfg,
    make_retrieval_run,
    ok_result,
    write_gate,
)

V2, V3 = "politica-reembolsos-v2#001", "politica-reembolsos-v3#001"
SLA = "sla#001"


def _rows(n=3, top=0.9):
    return [(f"q{i}", f"¿Pregunta {i}?", [V2, V3, SLA], top) for i in range(n)]


def _read(out):
    return [json.loads(x) for x in (out / "generations.jsonl").read_text("utf-8").splitlines()]


def _manifest(out):
    return json.loads((out / "gen_manifest.json").read_text("utf-8"))


def _run(tmp_path, rows, gen, cfg=None, gate=None, method="dense", **kw):
    run, index_root = make_retrieval_run(tmp_path, rows, method=method)
    cfg = cfg or fake_cfg()
    if gate is None:
        cfg = replace(cfg, gate_enabled=False)
    gate_path = write_gate(tmp_path, gate, method) if gate is not None else None
    return run_generation(
        run,
        cfg,
        gen,
        out_dir=tmp_path / "gen",
        index_root=index_root,
        gate_path=gate_path,
        sleep=lambda s: None,
        **kw,
    )


# --- gate -------------------------------------------------------------------------------


def test_gate_score_definitions():
    dense = [{"score": 0.91, "details": {}}, {"score": 0.80, "details": {}}]
    hybrid = [
        {"score": 0.03, "details": {"dense_score": 0.85}},
        {"score": 0.02, "details": {"dense_score": 0.90}},
        {"score": 0.01, "details": {}},  # sin rango dense: no aporta
    ]
    assert gate_score(dense, "dense") == 0.91
    assert gate_score(hybrid, "hybrid") == 0.90  # máx coseno, no el score RRF
    assert gate_score([], "dense") is None


def test_gate_abstains_without_calling_the_llm(tmp_path):
    gen = ScriptedGenerator([ok_result(ANSWER_S1)])
    rows = [("low", "¿baja?", [SLA], 0.80), ("high", "¿alta?", [V3], 0.95)]
    out = _run(tmp_path, rows, gen, gate=0.87)
    by = {r["qid"]: r for r in _read(out)}
    assert by["low"]["abstained"] and by["low"]["abstain_cause"] == "gate"
    assert by["low"]["llm"] is None and by["low"]["gate"]["passed"] is False
    assert by["high"]["abstained"] is False and by["high"]["gate"]["passed"]
    assert len(gen.prompts) == 1


def test_llm_abstention_is_recorded_with_its_cause(tmp_path):
    abstain = {
        "answer": "No hay información.",
        "citations": [],
        "abstain": True,
        "abstain_reason": "insufficient_evidence",
    }
    out = _run(tmp_path, _rows(1), ScriptedGenerator([ok_result(abstain)]), gate=0.5)
    r = _read(out)[0]
    assert r["abstained"] and r["abstain_cause"] == "llm"
    assert r["llm"]["parsed"]["abstain_reason"] == "insufficient_evidence"


def test_gate_from_eval_split_is_rejected(tmp_path):
    p = write_gate(tmp_path, 0.8)
    data = json.loads(p.read_text())
    data["calibration_split"] = "eval"
    p.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="calibration"):
        load_gate(p, {"run_name": "T_run"})


def test_gate_for_other_configuration_is_rejected(tmp_path):
    p = write_gate(tmp_path, 0.8, method="dense")
    manifest = {
        "run_name": "T_run",
        "index_id": "testindex0000000",
        "config_hash": "cfghash",
        "config": {"retrieval": {"method": "hybrid"}},
    }
    with pytest.raises(ValueError, match="method"):
        load_gate(p, manifest)


def test_calibrate_gate_refuses_eval_split(tmp_path):
    from rag_lab.evaluation.gate_calibration import calibrate_gate, compute_threshold

    run, _ = make_retrieval_run(tmp_path, _rows(1))
    with pytest.raises(ValueError, match="calibration"):
        calibrate_gate(run)
    assert compute_threshold([0.9, 0.95], [0.8]) == (0.85, True)
    assert compute_threshold([0.9, 0.95], [0.92]) == (0.9, False)


# --- citas y formato ---------------------------------------------------------------------


def test_invalid_citations_and_format_errors_are_recorded(tmp_path):
    bad_cite = ANSWER_S1 | {"citations": ["S1", "S7"]}
    gen = ScriptedGenerator([ok_result(bad_cite), ok_result("{no json")])
    out = _run(tmp_path, _rows(2), gen)
    r0, r1 = _read(out)
    assert r0["status"] == "ok" and r0["cited_chunk_ids"] == [V2]
    assert r0["llm"]["parsed"]["invalid_citations"] == ["S7"]
    assert r1["status"] == "format_error" and r1["answer"] is None
    assert len(gen.prompts) == 2  # el error de formato NO se reintenta


# --- errores de API, abortos y presupuesto ---------------------------------------------------


def test_api_error_is_recorded_and_run_continues(tmp_path):
    gen = ScriptedGenerator([ProviderError("bad_request", "400", 400), ok_result(ANSWER_S1)])
    out = _run(tmp_path, _rows(2), gen)
    r0, r1 = _read(out)
    assert r0["status"] == "api_error" and r0["llm"]["error"]["kind"] == "bad_request"
    assert r1["status"] == "ok"
    assert _manifest(out)["run_status"] == "complete"


def test_quota_429_stops_the_run(tmp_path):
    gen = ScriptedGenerator(
        [ok_result(ANSWER_S1), ProviderError("rate_limit", "q", 429, True, retry_after=9999)]
    )
    out = _run(tmp_path, _rows(4), gen)
    statuses = [r["status"] for r in _read(out)]
    assert statuses == ["ok", "not_run", "not_run", "not_run"]
    m = _manifest(out)
    assert m["run_status"] == "aborted" and "retry-after" in m["abort_reason"]
    assert len(gen.prompts) == 2


def test_consecutive_failures_stop_the_run(tmp_path):
    cfg = fake_cfg(max_consecutive_failures=2, max_retries=0)
    gen = ScriptedGenerator([ProviderError("server_error", "500", 500, transient=True)])
    out = _run(tmp_path, _rows(5), gen, cfg=cfg)
    statuses = [r["status"] for r in _read(out)]
    assert statuses[:2] == ["api_error", "api_error"] and set(statuses[2:]) == {"not_run"}
    assert len(gen.prompts) == 2


def test_call_budget_stops_the_run(tmp_path):
    cfg = fake_cfg(max_calls=2)
    gen = ScriptedGenerator([ok_result(ANSWER_S1)])
    out = _run(tmp_path, _rows(4), gen, cfg=cfg)
    assert [r["status"] for r in _read(out)] == ["ok", "ok", "not_run", "not_run"]
    assert "llamadas" in _manifest(out)["abort_reason"]
    assert len(gen.prompts) == 2


def test_token_budget():
    b = Budget(max_calls=10, max_tokens=100)
    b.reserve()
    b.add_tokens(120)
    with pytest.raises(BudgetExceeded, match="tokens"):
        b.reserve()


# --- caché -------------------------------------------------------------------------------


def test_cache_avoids_repeated_calls(tmp_path):
    cache = ResponseCache(tmp_path / "cache")
    gen = ScriptedGenerator([ok_result(ANSWER_S1)])
    run, index_root = make_retrieval_run(tmp_path, _rows(3))
    cfg = replace(fake_cfg(), gate_enabled=False)
    kw = {"index_root": index_root, "cache": cache, "sleep": lambda s: None}
    first = run_generation(run, cfg, gen, out_dir=tmp_path / "g1", **kw)
    second = run_generation(run, cfg, gen, out_dir=tmp_path / "g2", **kw)
    assert len(gen.prompts) == 3  # solo la primera corrida llama
    m1, m2 = _manifest(first), _manifest(second)
    assert m1["counts"]["llm_requests_real"] == 3 and m1["counts"]["cache_hits"] == 0
    assert m2["counts"]["llm_requests_real"] == 0 and m2["counts"]["cache_hits"] == 3
    assert m2["tokens_real"]["total_tokens"] == 0
    assert [r["answer"] for r in _read(first)] == [r["answer"] for r in _read(second)]


def test_cache_key_changes_with_parameters(tmp_path):
    cache = ResponseCache(tmp_path / "cache")
    gen = ScriptedGenerator([ok_result(ANSWER_S1)])
    run, index_root = make_retrieval_run(tmp_path, _rows(1))
    cfg = replace(fake_cfg(), gate_enabled=False)
    kw = {"index_root": index_root, "cache": cache, "sleep": lambda s: None}
    run_generation(run, cfg, gen, out_dir=tmp_path / "g1", **kw)
    hotter = replace(cfg, model=replace(cfg.model, temperature=0.3))
    run_generation(run, hotter, gen, out_dir=tmp_path / "g2", **kw)
    assert len(gen.prompts) == 2


def test_errors_are_not_cached(tmp_path):
    cache = ResponseCache(tmp_path / "cache")
    run, index_root = make_retrieval_run(tmp_path, _rows(1))
    cfg = replace(fake_cfg(), gate_enabled=False)
    kw = {"index_root": index_root, "cache": cache, "sleep": lambda s: None}
    failing = ScriptedGenerator([ProviderError("bad_request", "400", 400)])
    run_generation(run, cfg, failing, out_dir=tmp_path / "g1", **kw)
    good = ScriptedGenerator([ok_result(ANSWER_S1)])
    out = run_generation(run, cfg, good, out_dir=tmp_path / "g2", **kw)
    assert len(good.prompts) == 1 and _read(out)[0]["status"] == "ok"


# --- ritmo -------------------------------------------------------------------------------


def test_pacer_enforces_min_interval_and_waits_for_token_reset():
    now = [0.0]
    slept = []

    def sleep(s):
        slept.append(round(s, 3))
        now[0] += s

    p = Pacer(2.0, clock=lambda: now[0], sleep=sleep)
    p.wait_turn()
    p.wait_turn()
    assert slept == [2.0]
    r = ok_result(ANSWER_S1, tokens=3000)
    r.ratelimit = {"x-ratelimit-remaining-tokens": "1000", "x-ratelimit-reset-tokens": "20s"}
    p.observe(r)
    p.wait_turn()
    assert slept[-1] == pytest.approx(20.5)


# --- reproducibilidad offline ------------------------------------------------------------------


def test_offline_fake_pipeline_is_reproducible(tmp_path):
    rows = [*_rows(3), ("hist", "¿Cuál era el plazo antes de marzo de 2026?", [V3, V2], 0.95)]
    run, index_root = make_retrieval_run(tmp_path, rows)
    cfg = replace(fake_cfg(), gate_enabled=False)
    outs = [
        run_generation(run, cfg, FakeGenerator(), out_dir=tmp_path / f"g{i}", index_root=index_root)
        for i in range(2)
    ]
    a, b = ((o / "generations.jsonl").read_bytes() for o in outs)
    assert a == b
    by = {r["qid"]: r for r in _read(outs[0])}
    assert by["q0"]["cited_chunk_ids"] == [V3]  # vigente: ignora v2 aunque esté primero
    assert by["hist"]["cited_chunk_ids"] == [V2]  # histórica: usa v2


def test_concurrency_does_not_change_results(tmp_path):
    run, index_root = make_retrieval_run(tmp_path, _rows(6))
    outs = []
    for i, conc in enumerate((1, 3)):
        cfg = replace(fake_cfg(max_concurrency=conc), gate_enabled=False)
        outs.append(
            run_generation(
                run, cfg, FakeGenerator(), out_dir=tmp_path / f"c{i}", index_root=index_root
            )
        )
    assert (outs[0] / "generations.jsonl").read_bytes() == (
        outs[1] / "generations.jsonl"
    ).read_bytes()
