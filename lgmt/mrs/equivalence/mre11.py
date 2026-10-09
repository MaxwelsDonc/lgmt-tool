"""
MR-E1.1: Implication and Biconditional Elimination
"""
from typing import List, Tuple
from nltk.sem.logic import (
    Expression, 
    ImpExpression, 
    IffExpression, 
    AndExpression, 
    OrExpression, 
    NegatedExpression
)
from lgmt.mrs.equivalence.equivalence_utils import MetamorphicTransform, LogicTransformer

# =============================================================================
# MR-E1.1: Implication and Biconditional Elimination
# =============================================================================

class MRE11(MetamorphicTransform):
    def __init__(self):
        super().__init__(
            index="MR-E1.1", 
            name="Implication and Biconditional Elimination",
            transformer=self._Transformer(),
            logic_checker=None
        )

    # inner class: dedicated transformer
    class _Transformer(LogicTransformer):
        """
        [Inner class] AST rewriter dedicated to MR-E1.1.
        Inherits the traversal from LogicTransformer.
        """
        def transform(self, expr: Expression) -> Expression:
            # note: self here is the _Transformer instance
            # recurse into children via the base LogicTransformer
            if isinstance(expr, ImpExpression):
                # rule: P -> Q  =>  - P | Q
                left = self.recursive(expr.first)
                right = self.recursive(expr.second)
                return OrExpression(NegatedExpression(left), right)
            elif isinstance(expr, IffExpression):  
                # rule: P <-> Q => (~P | Q) & (~Q | P)
                left = self.recursive(expr.first)
                right = self.recursive(expr.second)
                
                part1 = OrExpression(NegatedExpression(left), right)
                part2 = OrExpression(NegatedExpression(right), left)
                return AndExpression(part1, part2)
            else:
                return self.recursive(expr)


    # =========================================================================
    # standard MR interface implementation
    # =========================================================================
    def source_templates(self) -> list[str]:
        return [ "A -> B", "A <-> B"]

    def check_applicability_logic(self, formula: str) -> bool:
        target_symbols = ["->", "<->"]
        return any(s in formula for s in target_symbols)

if __name__ == "__main__":
    # instantiate the MR to test
    mr = MRE11()
    
    # a few classic formulas (incl. unicode)
    test_cases = [
        "all x. (MichaelsNeightbor(x) & GrowIn(x, vegetable, garden) -> Have(x, ampleSpace))"
    ]
