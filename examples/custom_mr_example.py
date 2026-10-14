"""Example custom metamorphic relation for `lgmt build-mgs --mr-file`.

This is the same MR shown in the tool paper's Listing 1 and pre-filled in
the Web Studio's "Register Custom MR" drawer. It passes LGMT's built-in
Z3 equivalence verification on load.
"""
import copy

from nltk.sem.logic import LogicParser, NegatedExpression

from lgmt.core.structure import MetamorphicRelation, TestCase


class MRCxDoubleNegation(MetamorphicRelation):
    def __init__(self):
        self.index = "MR-CX"
        self.name = "Double Negation (Custom)"

    def check_applicability_logic(self, fol: str) -> bool:
        return bool(fol)

    def source_templates(self) -> list[str]:
        return []

    def check_applicability(self, tc: TestCase) -> bool:
        return bool(tc.conclusion_logic)

    def transform(self, tc: TestCase) -> TestCase:
        follow = copy.deepcopy(tc)
        ast = LogicParser().parse(tc.conclusion_logic)
        follow.conclusion_logic = str(NegatedExpression(NegatedExpression(ast)))
        follow.conclusion_text = (
            f"[Changed_conclusion] It is not the case that not ({tc.conclusion_text})"
        )
        return follow
