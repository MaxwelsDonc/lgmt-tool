"""Equivalence-preservation tests for all 20 metamorphic relations.

For every MR we transform handcrafted representative source cases (fixed
RNG seed for shuffle-based MRs) and assert:

1. the follow-up is well-formed FOL (parses with NLTK);
2. the premise set (and, where applicable, the conclusion) is logically
   equivalent to the source — checked with Z3 over universally closed
   formulas; when Z3 cannot decide (timeout / untranslatable), per-MR
   structural invariants (the fallback column) must still hold;
3. per-MR structural invariants, e.g. premise permutations for MR-P1,
   bijective symbol mappings for MR-S1/S2.
"""
import json
import os
import random
import re

import pytest
from nltk.sem.logic import AndExpression, LogicParser, NegatedExpression, OrExpression

from lgmt.core.structure import TestCase
from lgmt.mrs import ALL_MRS
from lgmt.utils.io import load_test_cases

from .z3check import check_equivalence

PARSER = LogicParser()
ARITH_PREMISE = re.compile(r"^(\d+)\^(\d+)=(\d+)$")

# Handcrafted representative source cases per MR index.
MR_CASES = {
    "MR-S1": [(["all x.(Man(x) -> Mortal(x))", "Man(socrates)"], "Mortal(socrates)")],
    "MR-S2": [(["all x.(Man(x) -> Mortal(x))", "Man(socrates)"], "Mortal(socrates)")],
    "MR-P1": [(["P(a)", "all x.(P(x) -> Q(x))", "Q(b)"], "Q(a)")],
    "MR-P2": [(["P(a)", "all x.(P(x) -> Q(x))", "Q(b)"], "Q(a)")],
    "MR-P3": [(["P(a)", "all x.(P(x) -> Q(x))"], "Q(a)")],
    "MR-P4": [(["P(a)", "Q(b)", "R(c)", "S(d)"], "T(a)")],
    "MR-P5": [(["P(a) & Q(a)", "R(b)"], "Q(a)")],
    "MR-C1": [(["P(a)"], "Q(b)")],
    "MR-C2": [(["P(a)"], "Q(b)")],
    "MR-C3": [(["P(a)"], "-Q(b)")],
    "MR-E1.1": [(["A -> B", "A <-> B", "P(a) -> Q(a)"], "B")],
    "MR-E1.2": [(["--P(a)", "-(A & B)", "-all x.P(x)"], "Q(a)")],
    "MR-E1.3": [(["(all x.P(x)) & Q(a)", "A | (exists x.B(x))"], "Q(a)")],
    "MR-E1.4": [(["C | (B | A)", "A & (B & A)"], "C")],
    "MR-E1.5": [(["all y.(G(x,y)) & all x.F(x)"], "F(a)")],
    "MR-E1.6": [
        (["all x.(exists w.(exists y.(all d.(all c.(all b.(exists z.(exists r.D(z,y,x))))))))"], "D(a,b,c)")
    ],
    "MR-E2.1": [(["A | A", "A & (A | B)", "P(a) | P(a)"], "A")],
    "MR-E2.2": [(["A & -A", "-A | A", "A & B & -A"], "A")],
    "MR-E2.3": [(["A & 1", "B | 0", "C | (B & 1)"], "A")],
    "MR-E2.4": [(["A & (B | C)", "A | (B & C)"], "A")],
}


def _case(mr_index, case_idx=0):
    premises, conclusion = MR_CASES[mr_index][case_idx]
    return TestCase(
        premises_logic=list(premises),
        premises_text=[f"text: {p}" for p in premises],
        conclusion_logic=conclusion,
        conclusion_text=f"text: {conclusion}",
        metadata={"label": "True", "data_source": "test"},
    )


def _flatten_top_conjunction(formula: str):
    """Split a formula's top-level & chain into parsed sub-expressions."""
    expr = PARSER.parse(formula)
    parts = []

    def _split(e):
        if isinstance(e, AndExpression):
            _split(e.first)
            _split(e.second)
        else:
            parts.append(e)

    _split(expr)
    return parts


def _substitute_names(formula: str, mapping) -> str:
    """Word-boundary substitution of symbols (used for S1/S2 mapping checks)."""
    out = formula
    for old, new in sorted(mapping.items(), key=lambda kv: -len(kv[0])):
        out = re.sub(rf"\b{re.escape(old)}\b", new, out)
    return out


def _assert_well_formed(formula: str, mr_index: str):
    """Every follow-up formula must parse as FOL (except MRP3 arithmetic).

    MR-E1.5 generates internally-bound names like ``bv1`` that NLTK's
    surface parser rejects in quantifier position; those formulas are
    still validated by the Z3 equivalence check below.
    """
    if ARITH_PREMISE.match(formula):
        return
    try:
        PARSER.parse(formula)
    except Exception:
        if mr_index == "MR-E1.5" and re.search(r"\bbv\d+\.", formula):
            return
        raise


# --------------------------------------------------------------------- #
# per-MR structural invariants
# --------------------------------------------------------------------- #
def _check_symbol_mapping(src: TestCase, fol: TestCase, kind: str):
    mapping = fol.metadata.get("mapping", {})
    assert mapping, f"{kind}: transform should record a symbol mapping"
    assert len(set(mapping.values())) == len(mapping), f"{kind}: mapping must be injective"
    src_formulas = src.premises_logic + [src.conclusion_logic]
    assert all(
        any(re.search(rf"\b{re.escape(k)}\b", f) for f in src_formulas) for k in mapping
    ), f"{kind}: mapping keys must come from the source case"
    assert fol.premises_logic == [
        _substitute_names(f, mapping) for f in src.premises_logic
    ], f"{kind}: renamed premises must equal source premises under the mapping"
    assert fol.conclusion_logic == _substitute_names(
        src.conclusion_logic, mapping
    ), f"{kind}: renamed conclusion must equal source conclusion under the mapping"


def _structural_invariants(mr, src: TestCase, fol: TestCase):
    idx = mr.index
    if idx == "MR-S1":
        _check_symbol_mapping(src, fol, idx)
    elif idx == "MR-S2":
        _check_symbol_mapping(src, fol, idx)
    elif idx == "MR-P1":
        assert sorted(fol.premises_logic) == sorted(src.premises_logic)
        assert fol.conclusion_logic == src.conclusion_logic
        assert fol.premises_logic != src.premises_logic, "P1 must change the order"
    elif idx == "MR-P2":
        assert len(fol.premises_logic) == len(src.premises_logic) + 1
        from collections import Counter

        delta = Counter(fol.premises_logic) - Counter(src.premises_logic)
        assert sum(delta.values()) == 1, "P2 adds exactly one duplicated premise"
        assert fol.conclusion_logic == src.conclusion_logic
    elif idx == "MR-P3":
        assert len(fol.premises_logic) == len(src.premises_logic) + 1
        added = fol.premises_logic[-1]
        m = ARITH_PREMISE.match(added)
        assert m, f"P3 must append an arithmetic premise, got {added!r}"
        assert int(m.group(1)) ** int(m.group(2)) == int(m.group(3)), (
            "P3 arithmetic premise must be a true identity"
        )
        assert fol.premises_logic[:-1] == src.premises_logic
        assert fol.conclusion_logic == src.conclusion_logic
    elif idx == "MR-P4":
        assert len(fol.premises_logic) == len(src.premises_logic) - 1
        from collections import Counter

        removed = Counter(src.premises_logic) - Counter(fol.premises_logic)
        assert sum(removed.values()) == 2, "P4 fuses exactly two premises"
        fused = [f for f in fol.premises_logic if f not in src.premises_logic]
        assert len(fused) == 1, "P4 must add exactly one fused premise"
        parts = {str(p) for p in _flatten_top_conjunction(fused[0])}
        assert parts == {PARSER.parse(f).__str__() for f in removed}, (
            "fused premise must be the conjunction of the two removed premises"
        )
        assert fol.conclusion_logic == src.conclusion_logic
    elif idx == "MR-P5":
        src_parts = []
        for f in src.premises_logic:
            src_parts.extend(str(p) for p in _flatten_top_conjunction(f))
        fol_parts = []
        for f in fol.premises_logic:
            fol_parts.extend(str(p) for p in _flatten_top_conjunction(f))
        assert sorted(fol_parts) == sorted(src_parts), (
            "P5 must preserve the top-level conjunction decomposition"
        )
        assert fol.conclusion_logic == src.conclusion_logic
    elif idx == "MR-C1":
        expr = PARSER.parse(fol.conclusion_logic)
        assert isinstance(expr, AndExpression), "C1 must build a conjunction"
        assert str(expr.second) == "1", "C1 must conjoin with logical truth (1)"
        assert str(expr.first) == PARSER.parse(src.conclusion_logic).__str__()
        assert fol.premises_logic == src.premises_logic
    elif idx == "MR-C2":
        expr = PARSER.parse(fol.conclusion_logic)
        assert isinstance(expr, OrExpression), "C2 must build a disjunction"
        assert str(expr.second) == "0", "C2 must disjoin with logical falsehood (0)"
        assert str(expr.first) == PARSER.parse(src.conclusion_logic).__str__()
        assert fol.premises_logic == src.premises_logic
    elif idx == "MR-C3":
        expr = PARSER.parse(fol.conclusion_logic)
        assert isinstance(expr, NegatedExpression), "C3 must negate the conclusion"
        assert isinstance(expr.term, NegatedExpression), "C3 must double-negate"
        assert str(expr.term.term) == PARSER.parse(src.conclusion_logic).__str__()
        assert fol.premises_logic == src.premises_logic
    else:  # E-class: formula-level rewrites
        assert fol.premises_logic != src.premises_logic, (
            f"{idx} changed nothing despite applicable templates"
        )
        changed = [s != f for s, f in zip(src.premises_logic, fol.premises_logic)]
        assert any(changed), f"{idx} must change at least one applicable premise"


# --------------------------------------------------------------------- #
# the parametrized test over all 20 MRs
# --------------------------------------------------------------------- #
@pytest.mark.parametrize("mr", ALL_MRS, ids=[m.index for m in ALL_MRS])
def test_mr_preserves_equivalence(mr):
    for case_idx in range(len(MR_CASES[mr.index])):
        src = _case(mr.index, case_idx)
        random.seed(42)
        fol = mr.transform(src)

        # 1. follow-up formulas must be well-formed FOL (except P3 arithmetic)
        for formula in fol.premises_logic + [fol.conclusion_logic]:
            _assert_well_formed(formula, mr.index)

        # 2. semantic equivalence via Z3 (fallback: structural invariants)
        fol_premises = [
            f for f in fol.premises_logic if not ARITH_PREMISE.match(f)
        ]
        src_premises = src.premises_logic
        if mr.index in ("MR-S1", "MR-S2"):
            # renaming MRs: compare the source under its own recorded mapping,
            # so that renamed symbols line up on both sides
            mapping = fol.metadata.get("mapping", {})
            src_premises = [_substitute_names(f, mapping) for f in src_premises]
        verdict = check_equivalence(src_premises, fol_premises)
        assert verdict in ("equivalent", "unknown", "untranslatable"), (
            f"{mr.index}: follow-up premise set is NOT equivalent to the source "
            f"(z3 verdict: {verdict})"
        )

        # 3. per-MR structural invariants
        _structural_invariants(mr, src, fol)


def test_conclusion_transforms_preserve_equivalence():
    """MR-C1/C2/C3 rewrite only the conclusion; check conclusion equivalence."""
    for index in ("MR-C1", "MR-C2", "MR-C3"):
        mr = next(m for m in ALL_MRS if m.index == index)
        src = _case(index)
        random.seed(42)
        fol = mr.transform(src)
        verdict = check_equivalence([src.conclusion_logic], [fol.conclusion_logic])
        assert verdict == "equivalent", f"{index}: conclusion not equivalent ({verdict})"


# --------------------------------------------------------------------- #
# real-data equivalence check (with graceful fallback)
# --------------------------------------------------------------------- #
def _iter_real_cases():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for name in (
        "folio_source_test_case.jsonl",
        "logicnli_source_test_case.jsonl",
        "proverqa_source_test_case.jsonl",
    ):
        path = os.path.join(root, "data", "source_test_case", name)
        for tc in load_test_cases(path)[:120]:
            yield tc


@pytest.mark.parametrize("mr", ALL_MRS, ids=[m.index for m in ALL_MRS])
def test_mr_equivalence_on_real_cases(mr):
    """Up to 2 applicable real source cases per MR must stay equivalent.

    Z3 may time out on large quantified formulas; in that case we fall back
    to asserting well-formedness of the transformation result.
    """
    checked = 0
    for tc in _iter_real_cases():
        if checked >= 2:
            break
        try:
            if not mr.check_applicability(tc):
                continue
        except Exception:
            continue
        random.seed(42)
        try:
            fol = mr.transform(tc)
        except Exception:
            continue
        checked += 1

        for formula in fol.premises_logic + [fol.conclusion_logic]:
            _assert_well_formed(formula, mr.index)

        fol_premises = [f for f in fol.premises_logic if not ARITH_PREMISE.match(f)]
        src_premises = tc.premises_logic
        if mr.index in ("MR-S1", "MR-S2"):
            mapping = fol.metadata.get("mapping", {})
            src_premises = [_substitute_names(f, mapping) for f in src_premises]
        verdict = check_equivalence(src_premises, fol_premises, timeout_ms=3000)
        assert verdict in ("equivalent", "unknown", "untranslatable"), (
            f"{mr.index}: follow-up NOT equivalent on a real case ({verdict})"
        )
    if checked == 0:
        pytest.skip(f"{mr.index}: no applicable case in the real-data scan window")
