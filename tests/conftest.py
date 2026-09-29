import os

import pytest

from lgmt.core.structure import TestCase
from lgmt.utils.io import load_metamorphic_groups

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEMO_MGS_PATH = os.path.join(REPO_ROOT, "lgmt", "demo", "demo_mgs.jsonl")


def make_case(premises, conclusion, label="True"):
    return TestCase(
        premises_logic=list(premises),
        premises_text=[f"text: {p}" for p in premises],
        conclusion_logic=conclusion,
        conclusion_text=f"text: {conclusion}",
        metadata={"label": label, "data_source": "test"},
    )


@pytest.fixture()
def demo_mgs():
    return load_metamorphic_groups(DEMO_MGS_PATH)


@pytest.fixture()
def demo_mgs_sample(demo_mgs):
    """A small, category-diverse demo subset (2 per MR category)."""
    by_category = {}
    for mg in demo_mgs:
        cat = mg.metadata.get("mr_index", "?").split("-")[1][0]
        by_category.setdefault(cat, []).append(mg)
    sample = []
    for cat in sorted(by_category):
        sample.extend(by_category[cat][:2])
    return sample
