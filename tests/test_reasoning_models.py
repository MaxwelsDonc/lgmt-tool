"""Reasoning-model compatibility of OpenAICompatClient.

Covers the deepseek-flash failure mode: reasoning models emit their answer
in ``reasoning_content`` (``content`` may be empty), and a token budget
consumed by reasoning yields ``finish_reason="length"``. Also: non-standard
provider error bodies must surface their detail and fail fast.
No real network traffic — the completions endpoint is replaced with a fake.
"""
from types import SimpleNamespace

import pytest

from lgmt.models.base import NonRetryableRequestError
from lgmt.models.openai_compat import OpenAICompatClient


class _FakeCompletions:
    """Scripted stand-in for client.chat.completions.create."""

    def __init__(self, script):
        self.script = list(script)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        step = self.script.pop(0)
        if isinstance(step, BaseException):
            raise step
        return step


def _client(script) -> tuple:
    client = OpenAICompatClient(
        api_key="sk-test", base_url="https://example.test/v1"
    )
    fake = _FakeCompletions(script)
    client.client = SimpleNamespace(
        chat=SimpleNamespace(completions=fake)
    )
    return client, fake


def _response(content="", reasoning_content=None, finish_reason="stop"):
    message = SimpleNamespace(content=content)
    if reasoning_content is not None:
        message.reasoning_content = reasoning_content
    choice = SimpleNamespace(message=message, finish_reason=finish_reason)
    return SimpleNamespace(choices=[choice])


def _api_error(status, body):
    """Mimic an openai.APIStatusError with a non-standard JSON body."""
    response = SimpleNamespace(status_code=status)
    response.json = lambda: body  # type: ignore[attr-defined]
    exc = Exception(f"Error code: {status} - {body}")
    exc.response = response  # type: ignore[attr-defined]
    exc.status_code = status  # type: ignore[attr-defined]
    return exc


PROMPT = {"system": "s", "user": "u"}


def test_reasoning_content_fallback_succeeds():
    client, fake = _client([
        _response(content="", reasoning_content='{"label": "True"}'),
    ])
    out = client.generate(PROMPT, model="deepseek-flash")
    assert out == '{"label": "True"}'
    assert len(fake.calls) == 1


def test_content_preferred_over_reasoning():
    client, _ = _client([
        _response(content='{"label": "False"}', reasoning_content="thinking..."),
    ])
    assert client.generate(PROMPT, model="deepseek-flash") == '{"label": "False"}'


def test_length_truncation_retries_with_raised_budget():
    client, fake = _client([
        _response(content="", reasoning_content="partial", finish_reason="length"),
        _response(content='{"label": "True"}', finish_reason="stop"),
    ])
    out = client.generate(PROMPT, model="deepseek-flash", max_tokens=4096)
    assert out == '{"label": "True"}'
    assert len(fake.calls) == 2
    # budget doubled on the retry
    assert fake.calls[0]["max_tokens"] == 4096
    assert fake.calls[1]["max_tokens"] == 8192
    # reasoning models still receive a max_tokens budget
    assert "max_tokens" in fake.calls[0]


def test_persistent_truncation_raises_with_guidance():
    client, fake = _client([
        _response(content="", finish_reason="length"),
        _response(content="", finish_reason="length"),
    ])
    with pytest.raises(NonRetryableRequestError) as exc:
        client.generate(PROMPT, model="deepseek-flash", max_retries=1, max_tokens=8192)
    assert "response truncated (finish_reason=length)" in str(exc.value)
    assert "consider raising max_tokens" in str(exc.value)


def test_truncation_retry_works_with_max_retries_zero():
    """Regression: the runner drives generate with max_retries=0, so the
    truncation retry must re-issue the request anyway (it used to fall out
    of the loop and return None, surfacing as a bogus 'Empty response')."""
    client, fake = _client([
        _response(content="partial", finish_reason="length"),
        _response(content='{"label": "True"}', finish_reason="stop"),
    ])
    out = client.generate(PROMPT, model="deepseek-flash", max_retries=0, max_tokens=4096)
    assert out == '{"label": "True"}'
    assert len(fake.calls) == 2
    assert fake.calls[0]["max_tokens"] == 4096
    assert fake.calls[1]["max_tokens"] == 8192


def test_persistent_truncation_with_max_retries_zero_raises():
    """Even with max_retries=0, staying truncated at the ceiling must raise
    the guidance error instead of returning None (which the runner would
    misreport as 'Empty response')."""
    client, fake = _client([
        _response(content="", finish_reason="length"),
        _response(content="", finish_reason="length"),
    ])
    with pytest.raises(NonRetryableRequestError) as exc:
        client.generate(PROMPT, model="deepseek-flash", max_retries=0, max_tokens=4096)
    assert "response truncated (finish_reason=length)" in str(exc.value)
    assert "consider raising max_tokens" in str(exc.value)
    assert len(fake.calls) == 2  # 4096 then 8192, then give up


def test_configured_budget_caps_ladder():
    """An explicit budget is used as-is; the auto-doubling ladder tops out
    at max(8192, budget) and never exceeds the configured value."""
    client, fake = _client([
        _response(content="", finish_reason="length"),
        _response(content='{"label": "True"}', finish_reason="stop"),
    ])
    out = client.generate(
        PROMPT, model="deepseek-reasoner", max_retries=0, max_tokens=6144
    )
    assert out == '{"label": "True"}'
    assert [c["max_tokens"] for c in fake.calls] == [6144, 8192]

    client2, fake2 = _client([_response(content="", finish_reason="length")])
    with pytest.raises(NonRetryableRequestError, match="consider raising max_tokens"):
        client2.generate(
            PROMPT, model="deepseek-reasoner", max_retries=0, max_tokens=32768
        )
    assert fake2.calls[0]["max_tokens"] == 32768  # large budget used as-is


def test_budget_omitted_by_default_and_escalates_to_65536():
    """Default: max_tokens is not sent at all (provider default — DeepSeek
    V4.1 allows ~384K output). On truncation the budget escalates
    8192 → 65536, never exceeding what the provider accepts."""
    client, fake = _client([
        _response(content="partial", finish_reason="length"),
        _response(content='{"label": "True"}', finish_reason="stop"),
    ])
    out = client.generate(PROMPT, model="deepseek-flash", max_retries=0)
    assert out == '{"label": "True"}'
    assert len(fake.calls) == 2
    assert "max_tokens" not in fake.calls[0]  # omitted, provider default
    assert fake.calls[1]["max_tokens"] == 8192

    client2, fake2 = _client([_response(content="", finish_reason="length")] * 5)
    with pytest.raises(NonRetryableRequestError) as exc:
        client2.generate(PROMPT, model="deepseek-flash", max_retries=0)
    assert "consider raising max_tokens" in str(exc.value)
    assert [c.get("max_tokens") for c in fake2.calls] == [
        None, 8192, 16384, 32768, 65536,
    ]


def test_400_fails_fast_with_provider_detail():
    """Providers reject unsupported budgets with 400 ("Invalid max_tokens
    param") — deterministic, so it must fail fast instead of retrying."""
    err = _api_error(400, {"message": "Invalid max_tokens param"})
    client, fake = _client([err])
    with pytest.raises(NonRetryableRequestError, match="Invalid max_tokens param"):
        client.generate(PROMPT, model="deepseek-flash", max_retries=2)
    assert len(fake.calls) == 1


def test_402_error_body_fails_fast_with_detail():
    err = _api_error(402, {"statusCode": 402, "message": "balance insufficient"})
    client, fake = _client([err])
    with pytest.raises(NonRetryableRequestError) as exc:
        client.generate(PROMPT, model="deepseek-flash")
    msg = str(exc.value)
    assert "402" in msg and "balance insufficient" in msg
    assert len(fake.calls) == 1  # no retries on 402


def test_401_fails_fast_but_429_retries():
    client, fake = _client([_api_error(401, {"message": "invalid key"})])
    with pytest.raises(NonRetryableRequestError, match="401"):
        client.generate(PROMPT, model="gpt-4o")
    assert len(fake.calls) == 1

    client2, fake2 = _client([
        _api_error(429, {"message": "rate limit"}),
        _response(content="ok"),
    ])
    out = client2.generate(PROMPT, model="gpt-4o", max_retries=1)
    assert out == "ok"
    assert len(fake2.calls) == 2  # 429 retried


def test_non_retryable_error_reaches_failed_record(demo_mgs_sample, tmp_path):
    """End-to-end: a 402 surfaces in the group's failed record, no 3x retry."""
    import json as _json

    from lgmt.core.runner import run_inference
    from lgmt.utils.io import load_inference_records

    client, fake = _client([_api_error(402, {"statusCode": 402, "message": "balance insufficient"})])
    results = str(tmp_path / "r.jsonl")
    run_inference(
        demo_mgs_sample[:1],
        client,
        "deepseek-flash",
        prompting="zero_direct",
        result_save_path=results,
        max_workers=1,
        quiet=True,
    )
    (record,) = load_inference_records(results)
    assert record["is_valid"] is False
    assert "402" in record["error"] and "balance insufficient" in record["error"]
    # call_llm must not retry a non-retryable error (1 attempt only)
    assert len(fake.calls) == 1


def test_truncation_mid_run_recovers_end_to_end(demo_mgs_sample, tmp_path):
    """Regression for the observed benchmark failure: deepseek-flash answers
    with finish_reason=length at the 4096 budget; the runner calls generate
    with max_retries=0, so the client must raise the budget itself and
    recover — the group must be judged valid, not recorded as failed."""
    from lgmt.core.runner import run_inference
    from lgmt.utils.io import load_inference_records

    script = []
    for _mg in demo_mgs_sample[:1]:
        # source: truncated at 4096, then complete at 8192; followup: fine
        script.append(_response(content="partial reasoning", finish_reason="length"))
        script.append(_response(content='{"label": "True"}', finish_reason="stop"))
        script.append(_response(content='{"label": "True"}', finish_reason="stop"))
    client, fake = _client(script)
    results = str(tmp_path / "r.jsonl")
    run_inference(
        demo_mgs_sample[:1],
        client,
        "deepseek-flash",
        prompting="zero_direct",
        result_save_path=results,
        max_workers=1,
        quiet=True,
        max_tokens=6144,
    )
    (record,) = load_inference_records(results)
    assert record["is_valid"] is True, record
    assert len(fake.calls) == 3
    # run_inference threads max_tokens through: 6144 -> 8192 on truncation
    assert fake.calls[0]["max_tokens"] == 6144
    assert fake.calls[1]["max_tokens"] == 8192
