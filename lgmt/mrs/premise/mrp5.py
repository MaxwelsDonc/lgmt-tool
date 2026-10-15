"""
MR-P5: Premise Decomposition
"""
import copy
import sys
import os


from typing import List, Tuple
from lgmt.core.structure import MetamorphicRelation, TestCase
from nltk.sem.logic import LogicParser, AndExpression

# =============================================================================
# MRP5: Premise Decomposition   
# =============================================================================

class MRP5(MetamorphicRelation):
    """Premise Decomposition (MR-P5)."""

    def __init__(self):
        self.index = "MR-P5"
        self.name = "Premise Decomposition"

    # =========================================================================
    # standard MR interface implementation
    # =========================================================================
    def check_applicability_logic(self, fol: str) -> bool:
        """
        Check whether this MR applies to the data.
        Splittable when a top-level (outside quantifiers) A & B structure exists.
        The check only looks for '&'; the transform decides actual splittability.
        """
        return "&" in fol

    def source_templates(self) -> List[str]:
        return []

    def check_applicability(self, test_case: TestCase) -> bool:
        """
        Check whether this MR applies to the data.
        Splittable when a top-level (outside quantifiers) A & B structure exists.
        The check only looks for '&'; the transform decides actual splittability.
        """
        premises_logic : List[str] = test_case.premises_logic
        return any(self.check_applicability_logic(s) for s in premises_logic)    
    
    def transform(self, source_TC: TestCase) -> TestCase:
        """
        Split premises:
        A top-level A & B premise splits into the A and B premises.
        Recursion: A & B & C -> A, B, C.
        Note: & inside quantifiers is not split (e.g. all x.(A(x) & B(x))).
        """
        follow_TC = copy.deepcopy(source_TC)
        new_premises_logic = []
        new_premises_text = []

        parser = LogicParser()

        def split_expression(expression) -> List[str]:
            """
            Recursively split AndExpressions
            """
            if isinstance(expression, AndExpression):
                # recurse into both sides
                return split_expression(expression.first) + split_expression(expression.second)
            else:
                # base case: keep the expression as-is
                return [str(expression)]

        # process every premise
        # enumerate for the source index
        for index, (p_logic, p_text) in enumerate(zip(source_TC.premises_logic, source_TC.premises_text)):
            try:
                # try to parse
                expr = parser.parse(p_logic)
                
                # split only top-level AndExpressions
                if isinstance(expr, AndExpression):
                    # splittable
                    split_parts = split_expression(expr)
                    
                    # append the split parts
                    for part in split_parts:
                        new_premises_logic.append(part)
                        # tag with Changed_{index}, the 0-based source premise index
                        new_premises_text.append(f"[Changed_{index}] {p_text}") 
                else:
                    # not splittable (e.g. all x.(A&B): top node is AllExpression)
                    new_premises_logic.append(p_logic)
                    new_premises_text.append(p_text)
                    
            except Exception as e:
                # unparseable premises pass through unchanged
                # print(f"Error parsing logic: {p_logic}, error: {e}")
                new_premises_logic.append(p_logic)
                new_premises_text.append(p_text)

        follow_TC.premises_logic = new_premises_logic
        follow_TC.premises_text = new_premises_text
        
        return follow_TC
