"""NL→FOL synthesis: pure-natural-language inputs get a synthesized FOL
skeleton (validated by NLTK's parser) before the MR pipeline runs."""
import json

import pytest

from lgmt.cli import main
from lgmt.core.builder import synthesize_missing_logic
from lgmt.models import MockLLMClient

NL_ONLY = {
    "premises_text": ["All dogs are mammals.", "Rex is a dog."],
    "conclusion_text": "Rex is a mammal.",
    "metadata": {"label": "True"},
}

FULL = {
    "premises_logic": ["all x.(Dog(x) -> Mammal(x))", "Dog(rex)"],
    "conclusion_logic": "Mammal(rex)",
    "premises_text": ["All dogs are mammals.", "Rex is a dog."],
    "conclusion_text": "Rex is a mammal.",
    "metadata": {"label": "True"},
}


def fake_translator(premises_text, conclusion_text):
    """Deterministic stand-in for the LLM translator (no API calls)."""
    return {
        "premises_logic": [f"Pred{i}(x)" for i, _ in enumerate(premises_text)],
        "conclusion_logic": "Concl(x)",
    }


def _write_jsonl(path, records):
    with open(path, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def test_synthesize_nl_only_record():
    out = synthesize_missing_logic([dict(NL_ONLY)], fake_translator)
    assert len(out) == 1
    assert out[0]["premises_logic"] == ["Pred0(x)", "Pred1(x)"]
    assert out[0]["conclusion_logic"] == "Concl(x)"
    # original NL text untouched
    assert out[0]["premises_text"] == NL_ONLY["premises_text"]


def test_synthesize_skips_complete_records():
    calls = []

    def counting_tr(premises_text, conclusion_text):
        calls.append(1)
        return fake_translator(premises_text, conclusion_text)

    out = synthesize_missing_logic([dict(FULL)], counting_tr)
    assert out[0] == FULL
    assert calls == []  # fully-specified records never reach the translator


def test_synthesize_mixed_input_only_translates_missing():
    calls = []

    def counting_tr(premises_text, conclusion_text):
        calls.append(tuple(premises_text))
        return fake_translator(premises_text, conclusion_text)

    out = synthesize_missing_logic([dict(FULL), dict(NL_ONLY)], counting_tr)
    assert len(out) == 2
    assert out[0] == FULL
    assert calls == [(NL_ONLY["premises_text"][0], NL_ONLY["premises_text"][1])] or calls == [
        tuple(NL_ONLY["premises_text"])
    ]


def test_invalid_translation_drops_case_with_warning():
    from loguru import logger

    def bad_translator(premises_text, conclusion_text):
        return {"premises_logic": ["not (parseable"], "conclusion_logic": "ok(x)"}

    messages = []
    sink_id = logger.add(lambda m: messages.append(str(m)), level="WARNING")
    try:
        out = synthesize_missing_logic([dict(NL_ONLY)], bad_translator)
    finally:
        logger.remove(sink_id)
    assert out == []
    assert any("NL→FOL synthesis failed" in m for m in messages)


def test_premise_count_mismatch_drops_case():
    def short_translator(premises_text, conclusion_text):
        return {"premises_logic": ["Only(x)"], "conclusion_logic": "Concl(x)"}

    assert synthesize_missing_logic([dict(NL_ONLY)], short_translator) == []


def test_cli_mock_rejects_nl_only_input(tmp_path, capsys):
    src = tmp_path / "nl.jsonl"
    _write_jsonl(src, [NL_ONLY])
    rc = main(
        [
            "build-mgs",
            "--input", str(src),
            "--output", str(tmp_path / "out.jsonl"),
            "--no-realize",
            "--mock", "consistent",
        ]
    )
    assert rc == 2
    err = capsys.readouterr().out
    assert "NL→FOL synthesis requires a real model" in err


def test_cli_missing_model_key_message(tmp_path, capsys, monkeypatch):
    monkeypatch.delenv("LGMT_API_KEY", raising=False)
    monkeypatch.delenv("LGMT_BASE_URL", raising=False)
    src = tmp_path / "nl.jsonl"
    _write_jsonl(src, [NL_ONLY])
    rc = main(
        [
            "build-mgs",
            "--input", str(src),
            "--output", str(tmp_path / "out.jsonl"),
            "--no-realize",
        ]
    )
    assert rc == 2
    out = capsys.readouterr().out
    assert "set LGMT_API_KEY or pass --model" in out
    assert "premises_logic/conclusion_logic" in out


def test_cli_full_field_input_unchanged_without_model(tmp_path, capsys):
    """Fully-specified inputs keep working with no model configured."""
    src = tmp_path / "full.jsonl"
    _write_jsonl(src, [FULL])
    rc = main(
        [
            "build-mgs",
            "--input", str(src),
            "--output", str(tmp_path / "out.jsonl"),
            "--no-realize",
            "--mock", "consistent",
        ]
    )
    assert rc == 0
    lines = open(tmp_path / "out.jsonl", encoding="utf-8").read().strip().splitlines()
    assert len(lines) >= 1
    assert '"premises_logic"' in lines[0]
