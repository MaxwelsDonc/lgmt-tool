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
