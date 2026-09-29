"""Label canonicalization: the tool uses "Unknown"; legacy "Uncertain"
spelling (older prompts and result files) must be accepted and normalized."""
import pytest

from lgmt.utils.labels import canonical_label


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("True", "True"),
        ("true", "True"),
        ("TRUE", "True"),
        ("False", "False"),
        ("false", "False"),
        ("Unknown", "Unknown"),
        ("unknown", "Unknown"),
        ("Uncertain", "Unknown"),
        ("uncertain", "Unknown"),
        ("UNCERTAIN", "Unknown"),
        ("", "Unknown"),
        (None, "Unknown"),
        ("yes", "Unknown"),
        ("Entailment", "Unknown"),
    ],
)
def test_canonical_label(raw, expected):
    assert canonical_label(raw) == expected
