"""Regression tests for runner plumbing (S4): temperature pass-through."""
import json

from lgmt.core.runner import run_inference
from lgmt.models.base import LLMClient


class RecordingClient(LLMClient):
    """Captures generate() kwargs; answers with a fixed valid verdict."""

    def __init__(self):
        self.calls = []

    def generate(self, prompt_data, model=None, **kwargs):
        self.calls.append(kwargs)
        return json.dumps({"reasoning": "r", "label": "True"})


def _two_mgs(demo_mgs_sample):
    return demo_mgs_sample[:2]


def test_temperature_forwarded_to_client(demo_mgs_sample, tmp_path):
    client = RecordingClient()
    run_inference(
        _two_mgs(demo_mgs_sample),
        client,
        "recorder",
        prompting="zero_cot",
        result_save_path=str(tmp_path / "r.jsonl"),
        max_workers=2,
        quiet=True,
        temperature=0.7,
    )
    # 2 MGs x 2 calls (source + follow-up)
    assert len(client.calls) == 4
    assert all(c.get("temperature") == 0.7 for c in client.calls)


def test_temperature_defaults_to_zero(demo_mgs_sample, tmp_path):
    client = RecordingClient()
    run_inference(
        _two_mgs(demo_mgs_sample),
        client,
        "recorder",
        prompting="zero_direct",
        result_save_path=str(tmp_path / "r.jsonl"),
        max_workers=1,
        quiet=True,
    )
    assert len(client.calls) == 4
    assert all(c.get("temperature") == 0.0 for c in client.calls)
