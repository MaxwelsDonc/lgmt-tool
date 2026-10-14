"""Z3-based equivalence verification for (custom) metamorphic relations.

Each MR is exercised on a fixed battery of standard FOL samples covering
universal quantification, implication, conjunction/disjunction, negation,
and biconditionals. For every sample the MR applies to, the follow-up
must be entailment-equivalent to the source — ``(∧ Γ_s → q_s) ↔ (∧ Γ_f →
q_f)`` validated with Z3 over universally closed formulas.
"""
from typing import Any, Dict, List

from nltk.sem.logic import LogicParser

from lgmt.core.structure import TestCase
from lgmt.utils.z3check import check_entailment_equivalence

#: Standard verification samples: (premises, conclusion).
STANDARD_SAMPLES: List[tuple] = [
    (["all x.(P(x) -> Q(x))", "P(a)"], "Q(a)"),            # universal + modus ponens
    (["A & B"], "A | B"),                                  # conjunction -> disjunction
    (["-(A | B)"], "-A & -B"),                             # De Morgan
    (["exists x.(R(x) & S(x))", "all x.(S(x) -> T(x))"], "exists x.(R(x) & T(x))"),  # existential
    (["A <-> B", "A"], "B"),                               # biconditional elimination
]


def verify_mr_equivalence_with_z3(mr) -> Dict[str, Any]:
    """Verify ``mr`` on the standard samples; raise ValueError on any failure.

    Returns ``{"verified_count": k, "tested": n}`` where ``k`` is the number
    of applicable samples verified equivalent and ``n`` the number of
    applicable samples.
    """
    parser = LogicParser()
    verified = 0
    tested = 0
    failures = []
    for premises, conclusion in STANDARD_SAMPLES:
        tc = TestCase(
            premises_logic=list(premises),
            conclusion_logic=conclusion,
            premises_text=list(premises),
            conclusion_text=conclusion,
            metadata={"label": "True"},
        )
        try:
            applicable = mr.check_applicability(tc)
        except Exception as e:
            raise ValueError(
                f"check_applicability raised on sample {premises!r}: {e}"
            ) from e
        if not applicable:
            continue
        tested += 1
        try:
            follow = mr.transform(tc)
        except Exception as e:
            raise ValueError(f"transform raised on sample {premises!r}: {e}") from e
        # both sides must be well-formed FOL
        try:
            for f in list(follow.premises_logic) + [follow.conclusion_logic]:
                parser.parse(f)
            for f in list(tc.premises_logic) + [tc.conclusion_logic]:
                parser.parse(f)
        except Exception as e:
            raise ValueError(
                f"transform output is not parseable FOL on sample {premises!r}: {e}"
            ) from e
        verdict = check_entailment_equivalence(
            tc.premises_logic,
            tc.conclusion_logic,
            list(follow.premises_logic),
            follow.conclusion_logic,
        )
        if verdict == "equivalent":
            verified += 1
        else:
            failures.append(
                f"sample {premises!r} => {conclusion!r}: Z3 verdict={verdict} "
                "(follow-up not equivalent / undecided)"
            )
    if failures:
        raise ValueError(
            f"MR {getattr(mr, 'index', '?')} failed Z3 equivalence: " + "; ".join(failures)
        )
    return {"verified_count": verified, "tested": tested}
