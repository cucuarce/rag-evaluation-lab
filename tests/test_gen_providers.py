"""Errores de red, timeout, 429 y 5xx: política de reintentos y mapeo del SDK de Groq."""

from __future__ import annotations

import json

import httpx
import pytest

from rag_lab.generation.config import load_generation_config
from rag_lab.generation.prompt import ANSWER_SCHEMA
from rag_lab.generation.providers import (
    AbortRun,
    GroqGenerator,
    ProviderError,
    call_with_retries,
    parse_reset,
)
from tests.gen_helpers import GROQ_CFG, ok_result

FAKE_KEY = "gsk_test_not_a_real_key_0123456789"
MESSAGES = [{"role": "user", "content": "hola"}]


@pytest.fixture
def limits():
    return load_generation_config(GROQ_CFG).limits


def _seq(*items):
    items = list(items)

    def fn():
        item = items.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    return fn


def test_transient_errors_are_retried_with_backoff(limits):
    sleeps = []
    fn = _seq(
        ProviderError("timeout", "t", transient=True),
        ProviderError("server_error", "5xx", 503, transient=True),
        ok_result({"x": 1}),
    )
    res = call_with_retries(fn, limits, sleep=sleeps.append)
    assert res.attempts == 3 and len(res.errors) == 2
    assert sleeps == [limits.backoff_base_s, limits.backoff_base_s * 2]


def test_retries_are_bounded(limits):
    errors = [ProviderError("server_error", "5xx", 500, transient=True)] * 10
    with pytest.raises(ProviderError) as exc:
        call_with_retries(_seq(*errors), limits, sleep=lambda s: None)
    assert exc.value.attempts == limits.max_retries + 1


def test_short_429_uses_retry_after(limits):
    sleeps = []
    fn = _seq(ProviderError("rate_limit", "429", 429, True, retry_after=3.0), ok_result({}))
    call_with_retries(fn, limits, sleep=sleeps.append)
    assert sleeps == [3.0]


def test_long_429_aborts_the_run(limits):
    fn = _seq(ProviderError("rate_limit", "quota", 429, True, retry_after=3600.0))
    with pytest.raises(AbortRun, match="retry-after"):
        call_with_retries(fn, limits, sleep=lambda s: None)


def test_auth_error_aborts_without_retry(limits):
    sleeps = []
    with pytest.raises(AbortRun):
        call_with_retries(_seq(ProviderError("auth", "bad key", 401)), limits, sleeps.append)
    assert sleeps == []


def test_bad_request_is_not_retried(limits):
    calls = []

    def fn():
        calls.append(1)
        raise ProviderError("bad_request", "400", 400)

    with pytest.raises(ProviderError):
        call_with_retries(fn, limits, sleep=lambda s: None)
    assert len(calls) == 1


@pytest.mark.parametrize(
    ("value", "seconds"),
    [("7.66s", 7.66), ("2m59.56s", 179.56), ("350ms", 0.35), ("12", 12.0), (None, None)],
)
def test_parse_reset(value, seconds):
    assert parse_reset(value) == pytest.approx(seconds) if seconds else parse_reset(value) is None


# --- Mapeo real del SDK de Groq con un transporte HTTP simulado (sin red) ----------------


def _client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def _gen(handler):
    return GroqGenerator(load_generation_config(GROQ_CFG), FAKE_KEY, http_client=_client(handler))


COMPLETION = {
    "id": "chatcmpl-1",
    "object": "chat.completion",
    "created": 0,
    "model": "openai/gpt-oss-120b",
    "choices": [
        {
            "index": 0,
            "finish_reason": "stop",
            "message": {
                "role": "assistant",
                "content": json.dumps(
                    {"answer": "a", "citations": ["S1"], "abstain": False, "abstain_reason": "none"}
                ),
            },
        }
    ],
    "usage": {
        "prompt_tokens": 100,
        "completion_tokens": 50,
        "total_tokens": 150,
        "completion_tokens_details": {"reasoning_tokens": 30},
    },
}


def test_groq_success_request_shape_usage_and_headers():
    seen = {}

    def handler(request: httpx.Request):
        seen["body"] = json.loads(request.content)
        seen["auth"] = request.headers["authorization"]
        return httpx.Response(
            200,
            json=COMPLETION,
            headers={"x-ratelimit-remaining-tokens": "7000", "x-request-id": "req_1"},
        )

    res = _gen(handler).generate(MESSAGES, ANSWER_SCHEMA)
    body = seen["body"]
    assert body["model"] == "openai/gpt-oss-120b"
    assert body["response_format"]["type"] == "json_schema"
    assert body["response_format"]["json_schema"]["strict"] is True
    assert body["temperature"] == 0.2 and body["include_reasoning"] is False
    assert res.usage == {
        "prompt_tokens": 100,
        "completion_tokens": 50,
        "total_tokens": 150,
        "reasoning_tokens": 30,
    }
    assert res.ratelimit["x-ratelimit-remaining-tokens"] == "7000"
    assert res.request_id == "req_1"
    # La clave viaja solo en el encabezado HTTP, nunca en el resultado.
    assert seen["auth"] == f"Bearer {FAKE_KEY}"
    assert FAKE_KEY not in json.dumps(res.to_record())


@pytest.mark.parametrize(
    ("status", "headers", "kind", "transient", "retry_after"),
    [
        (429, {"retry-after": "7"}, "rate_limit", True, 7.0),
        (500, {}, "server_error", True, None),
        (503, {}, "server_error", True, None),
        (401, {}, "auth", False, None),
        (404, {}, "not_found", False, None),
        (400, {}, "bad_request", False, None),
    ],
)
def test_groq_http_errors_are_mapped(status, headers, kind, transient, retry_after):
    def handler(request):
        return httpx.Response(status, json={"error": {"message": "boom"}}, headers=headers)

    with pytest.raises(ProviderError) as exc:
        _gen(handler).generate(MESSAGES, ANSWER_SCHEMA)
    e = exc.value
    assert (e.kind, e.transient, e.retry_after) == (kind, transient, retry_after)
    assert FAKE_KEY not in e.message


@pytest.mark.parametrize(
    ("exc", "kind"),
    [(httpx.ReadTimeout("t"), "timeout"), (httpx.ConnectError("refused"), "connection")],
)
def test_groq_network_errors_are_transient(exc, kind):
    def handler(request):
        raise exc

    with pytest.raises(ProviderError) as err:
        _gen(handler).generate(MESSAGES, ANSWER_SCHEMA)
    assert err.value.kind == kind and err.value.transient


def test_groq_sdk_does_not_retry_on_its_own():
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(500, json={"error": {"message": "x"}})

    with pytest.raises(ProviderError):
        _gen(handler).generate(MESSAGES, ANSWER_SCHEMA)
    assert len(calls) == 1


def test_missing_api_key_is_rejected():
    with pytest.raises(ValueError):
        GroqGenerator(load_generation_config(GROQ_CFG), "")
