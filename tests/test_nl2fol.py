"""NL→FOL synthesis, Pure FOL auto-detection, and Unstructured extraction tests."""
import json

from lgmt.cli import main
from lgmt.core.builder import (
    looks_like_fol,
    make_nl2fol_translator,
    make_unstructured_extractor,
    synthesize_missing_logic,
)
from lgmt.models.base import LLMClient
from lgmt.webapp import _parse_source_cases


class FakeTranslatorClient(LLMClient):
    """Returns canned JSON responses for NL→FOL translation and extraction."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0

    def generate(self, prompt_data, model=None, **kwargs):
        resp = self.responses[min(self.calls, len(self.responses) - 1)]
        self.calls += 1
        return resp


def test_synthesize_nl_only_record():
    client = FakeTranslatorClient(
        [
            json.dumps(
                {
                    "premises_logic": [
                        "all x. (Patient(x) -> Recovers(x))",
                        "Patient(alice)",
                    ],
                    "conclusion_logic": "Recovers(alice)",
                }
            )
        ]
    )
    translator = make_nl2fol_translator(client, "fake-model")
    records = [
        {
            "premises_text": [
                "Every patient recovers.",
                "Alice is a patient.",
            ],
            "conclusion_text": "Alice recovers.",
        }
    ]
    out = synthesize_missing_logic(records, translator)
    assert len(out) == 1
    assert out[0]["premises_logic"] == [
        "all x. (Patient(x) -> Recovers(x))",
        "Patient(alice)",
    ]
    assert out[0]["conclusion_logic"] == "Recovers(alice)"
    assert client.calls == 1


def test_synthesize_skips_complete_records():
    client = FakeTranslatorClient([])
    translator = make_nl2fol_translator(client, "fake-model")
    records = [
        {
            "premises_logic": ["all x. (P(x) -> Q(x))", "P(a)"],
            "conclusion_logic": "Q(a)",
            "premises_text": ["All P are Q.", "a is P."],
            "conclusion_text": "a is Q.",
        }
    ]
    out = synthesize_missing_logic(records, translator)
    assert len(out) == 1
    assert client.calls == 0


def test_pure_fol_records_auto_fill_text_without_llm():
    # Pure FOL via premises_logic/conclusion_logic (no premises_text)
    records = [
        {
            "premises_logic": ["all x. (Bird(x) -> Fly(x))", "Bird(tweety)"],
            "conclusion_logic": "Fly(tweety)",
        }
    ]
    out = synthesize_missing_logic(records, translator=None)
    assert len(out) == 1
    assert out[0]["premises_text"] == ["all x. (Bird(x) -> Fly(x))", "Bird(tweety)"]
    assert out[0]["conclusion_text"] == "Fly(tweety)"

    # Pure FOL typed directly inside premises_text/conclusion_text (e.g. Quick Form)
    form_records = [
        {
            "premises_text": ["all x. (Bird(x) -> Fly(x))", "Bird(tweety)"],
            "conclusion_text": "Fly(tweety)",
        }
    ]
    out2 = synthesize_missing_logic(form_records, translator=None)
    assert len(out2) == 1
    assert out2[0]["premises_logic"] == ["all x. (Bird(x) -> Fly(x))", "Bird(tweety)"]
    assert out2[0]["conclusion_logic"] == "Fly(tweety)"
    assert looks_like_fol("all x. (Bird(x) -> Fly(x))")
    assert not looks_like_fol("Every patient who takes the medication recovers.")


def test_unstructured_paragraph_extraction_and_chinese_nl2fol():
    client = FakeTranslatorClient(
        [
            json.dumps(
                {
                    "premises_text": [
                        "所有在胁迫下签署的合同都是可撤销的。",
                        "Smith合同是在胁迫下签署的。",
                    ],
                    "conclusion_text": "Smith合同是可撤销的。",
                }
            ),
            json.dumps(
                {
                    "premises_logic": [
                        "all x. (SignedUnderDuress(x) -> Voidable(x))",
                        "SignedUnderDuress(smith_contract)",
                    ],
                    "conclusion_logic": "Voidable(smith_contract)",
                }
            ),
        ]
    )
    extractor = make_unstructured_extractor(client, "fake-model")
    translator = make_nl2fol_translator(client, "fake-model")
    paragraph = "所有在胁迫下签署的合同都是可撤销的。Smith合同是在胁迫下签署的。因此，Smith合同是可撤销的。"
    cases = _parse_source_cases(
        paragraph,
        translator=translator,
        extractor=extractor,
        input_mode="unstructured",
    )
    assert len(cases) == 1
    assert cases[0].premises_text[0] == "所有在胁迫下签署的合同都是可撤销的。"
    assert cases[0].conclusion_logic == "Voidable(smith_contract)"


def test_synthesize_mixed_input_only_translates_missing():
    client = FakeTranslatorClient(
        [
            json.dumps(
                {
                    "premises_logic": ["P(a)"],
                    "conclusion_logic": "P(a)",
                }
            )
        ]
    )
    translator = make_nl2fol_translator(client, "fake-model")
    records = [
        {
            "premises_logic": ["all x. (P(x) -> Q(x))"],
            "conclusion_logic": "Q(a)",
            "premises_text": ["All P are Q."],
            "conclusion_text": "a is Q.",
        },
        {
            "premises_text": ["a has property P."],
            "conclusion_text": "a has property P.",
        },
    ]
    out = synthesize_missing_logic(records, translator)
    assert len(out) == 2
    assert client.calls == 1
    assert out[1]["conclusion_logic"] == "P(a)"


def test_invalid_translation_drops_case_with_warning():
    client = FakeTranslatorClient(
        [
            json.dumps(
                {
                    "premises_logic": ["not valid nltk ((( syntax"],
                    "conclusion_logic": "Q(a)",
                }
            )
        ]
    )
    translator = make_nl2fol_translator(client, "fake-model")
    records = [
        {
            "premises_text": ["Some sentence."],
            "conclusion_text": "Some conclusion.",
        }
    ]
    out = synthesize_missing_logic(records, translator, retries=1)
    assert out == []
    assert client.calls == 2


def test_premise_count_mismatch_drops_case():
    client = FakeTranslatorClient(
        [
            json.dumps(
                {
                    "premises_logic": ["P(a)"],  # only 1 formula for 2 premises
                    "conclusion_logic": "Q(a)",
                }
            )
        ]
    )
    translator = make_nl2fol_translator(client, "fake-model")
    records = [
        {
            "premises_text": ["Premise one.", "Premise two."],
            "conclusion_text": "Conclusion.",
        }
    ]
    out = synthesize_missing_logic(records, translator, retries=0)
    assert out == []


def test_cli_mock_rejects_nl_only_input(tmp_path, capsys):
    inp = tmp_path / "nl.jsonl"
    out = tmp_path / "mgs.jsonl"
    inp.write_text(
        json.dumps(
            {
                "premises_text": ["All humans are mortal.", "Socrates is human."],
                "conclusion_text": "Socrates is mortal.",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    rc = main(
        [
            "build-mgs",
            "--input",
            str(inp),
            "--output",
            str(out),
            "--mock",
            "consistent",
        ]
    )
    assert rc == 2
    err = capsys.readouterr().out
    assert "NL→FOL synthesis requires a real model" in err


def test_cli_missing_model_key_message(tmp_path, capsys, monkeypatch):
    monkeypatch.delenv("LGMT_API_KEY", raising=False)
    inp = tmp_path / "nl.jsonl"
    out = tmp_path / "mgs.jsonl"
    inp.write_text(
        json.dumps(
            {
                "premises_text": ["All humans are mortal.", "Socrates is human."],
                "conclusion_text": "Socrates is mortal.",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    rc = main(["build-mgs", "--input", str(inp), "--output", str(out)])
    assert rc == 2
    out_text = capsys.readouterr().out
    assert "NL→FOL synthesis requires a model" in out_text


def test_cli_full_field_input_unchanged_without_model(tmp_path, capsys):
    inp = tmp_path / "full.jsonl"
    out = tmp_path / "mgs.jsonl"
    inp.write_text(
        json.dumps(
            {
                "premises_logic": ["all x. (Man(x) -> Mortal(x))", "Man(socrates)"],
                "conclusion_logic": "Mortal(socrates)",
                "premises_text": ["All men are mortal.", "Socrates is a man."],
                "conclusion_text": "Socrates is mortal.",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    rc = main(
        ["build-mgs", "--input", str(inp), "--output", str(out), "--no-realize"]
    )
    assert rc == 0
    assert out.exists() and out.stat().st_size > 0
