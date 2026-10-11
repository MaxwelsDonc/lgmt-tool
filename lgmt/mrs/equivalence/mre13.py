"""
MR-E1.3: Quantifier Lifting
"""
from typing import List, Tuple
from nltk.sem.logic import (
    Expression, 
    AndExpression, 
    OrExpression, 
    ExistsExpression,
    AllExpression,
    IndividualVariableExpression
)
from lgmt.mrs.equivalence.equivalence_utils import MetamorphicTransform, LogicTransformer, LogicChecker, get_indiv_vars

# =============================================================================
# MR-E1.3: Quantifier Lifting
# =============================================================================

class MRE13(MetamorphicTransform):
    def __init__(self):
        super().__init__(
            index="MR-E1.3", 
            name="Quantifier Lifting",
            transformer=self._Transformer(),
            logic_checker=self._LogicChecker()
        )

    # inner class: dedicated transformer
    class _Transformer(LogicTransformer):
        """
        [Inner class] AST rewriter dedicated to MR-E1.3.
        Inherits the traversal from LogicTransformer.
        """
        def transform(self, expr: Expression) -> Expression:
            """
            Rule: inspect & / | chains for All/Exists sub-expressions.
            """
            if isinstance(expr, (AndExpression, OrExpression)):
                if (isinstance(expr.first, (AllExpression, ExistsExpression)) and 
                    IndividualVariableExpression(expr.first.variable) not in get_indiv_vars(expr.second)):
                    return expr.first.__class__(expr.first.variable, self.transform(expr.__class__(
                        expr.first.term, expr.second
                    )))
                elif (isinstance(expr.second, (AllExpression, ExistsExpression)) and 
                    IndividualVariableExpression(expr.second.variable) not in get_indiv_vars(expr.first)):
                    return expr.second.__class__(expr.second.variable, self.transform(expr.__class__(
                        expr.first, expr.second.term
                    )))
                else:
                    return self.recursive(expr)
            else:
                return self.recursive(expr)
            
            
    # inner class: dedicated checker
    class _LogicChecker(LogicChecker):
        """
        [Inner class] AST rewriter dedicated to MR-E1.3.
        Inherits the traversal from LogicChecker.
        """
        def check(self, expr: Expression) -> bool:
            """
            Rule: inspect & / | chains for All/Exists sub-expressions.
            """
            if isinstance(expr, (AndExpression, OrExpression)):
                if (isinstance(expr.first, (AllExpression, ExistsExpression)) and 
                    IndividualVariableExpression(expr.first.variable) not in get_indiv_vars(expr.second)):
                    return True
                elif (isinstance(expr.second, (AllExpression, ExistsExpression)) and 
                    IndividualVariableExpression(expr.second.variable) not in get_indiv_vars(expr.first)):
                    return True
                else:
                    return self.check(expr.first) | self.check(expr.second)
            else:
                return self.recursive(expr)

    # =========================================================================
    # standard MR interface implementation
    # =========================================================================
    def source_templates(self) -> list[str]:
        return [
            "(all x.A) & B", 
            "(all x.A(x) & B(x))",
            "A | (exists x.B)",
        ]
