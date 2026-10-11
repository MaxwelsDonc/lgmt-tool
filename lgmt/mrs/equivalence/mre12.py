"""
MR-E1.2: Negation Normalization
"""
from typing import List, Tuple
from nltk.sem.logic import (
    Expression, 
    AndExpression, 
    OrExpression, 
    NegatedExpression,
    ExistsExpression,
    AllExpression
)
from lgmt.mrs.equivalence.equivalence_utils import MetamorphicTransform, LogicTransformer, LogicChecker

# =============================================================================
# MR-E1.2: Negation Normalization
# =============================================================================

class MRE12(MetamorphicTransform):
    def __init__(self):
        super().__init__(
            index="MR-E1.2", 
            name="Negation Normalization",
            transformer=self._Transformer(),
            logic_checker=self._LogicChecker()
        )

    # inner class: dedicated transformer
    class _Transformer(LogicTransformer):
        """
        [Inner class] AST rewriter dedicated to MR-E1.2.
        Inherits the traversal from LogicTransformer.
        """
        def transform(self, expr: Expression) -> Expression:
            """
            Rule: strip the leading ~, then inspect the negated expression.
            """
            if isinstance(expr, NegatedExpression):
                if isinstance(expr.term, NegatedExpression):
                    return self.recursive(expr.term.term)
                elif isinstance(expr.term, AndExpression):
                    return OrExpression(NegatedExpression(self.recursive(expr.term.first)), NegatedExpression(self.recursive(expr.term.second)))
                elif isinstance(expr.term, OrExpression):
                    return AndExpression(NegatedExpression(self.recursive(expr.term.first)), NegatedExpression(self.recursive(expr.term.second)))
                elif isinstance(expr.term, AllExpression):
                    return ExistsExpression(expr.term.variable, NegatedExpression(self.recursive(expr.term.term)))
                elif isinstance(expr.term, ExistsExpression):
                    return AllExpression(expr.term.variable, NegatedExpression(self.recursive(expr.term.term)))
                else:
                    return self.recursive(expr)
            else:
                return self.recursive(expr)
            
    # inner class: dedicated checker
    class _LogicChecker(LogicChecker):
        """
        [Inner class] AST rewriter dedicated to MR-E1.2.
        Inherits the traversal from LogicChecker.
        """
        def check(self, expr: Expression) -> bool:
            """
            Rule: strip the leading ~, then inspect the negated expression.
            """
            if isinstance(expr, NegatedExpression):
                if isinstance(expr.term, NegatedExpression):
                    return True
                elif isinstance(expr.term, AndExpression):
                    return True
                elif isinstance(expr.term, OrExpression):
                    return True
                elif isinstance(expr.term, AllExpression):
                    return True
                elif isinstance(expr.term, ExistsExpression):
                    return True
                else:
                    return self.recursive(expr.term)
            else:
                return self.recursive(expr)

    # =========================================================================
    # standard MR interface implementation
    # =========================================================================
    def source_templates(self) -> list[str]:
        return ["--A", "-( A & B )", "-( A | B )", "-all x.A", "-exists x.A"]
