"""
MR-E1.4: Structural Normalization
"""
from functools import reduce
import operator
from typing import List, Tuple
from nltk.sem.logic import (
    Expression, 
    AndExpression, 
    OrExpression, 
)
from lgmt.mrs.equivalence.equivalence_utils import MetamorphicTransform, LogicTransformer, LogicChecker, get_indiv_vars

# =============================================================================
# MR-E1.4: Structural Normalization
# =============================================================================

class MRE14(MetamorphicTransform):
    def __init__(self):
        super().__init__(
            index="MR-E1.4", 
            name="Structural Normalization",
            transformer=self._Transformer(),
            logic_checker=self._LogicChecker()
        )

    # inner class: dedicated transformer
    class _Transformer(LogicTransformer):
        """
        [Inner class] AST rewriter dedicated to MR-E1.4.
        Inherits the traversal from LogicTransformer.
        """
        def transform(self, expr: Expression) -> Expression:
            """
            Rule: recursively flatten & / | and sort by string.
            """
            if isinstance(expr, (AndExpression, OrExpression)):
                elements = []
                def reduction(sub_expr: AndExpression | OrExpression, target_class):
                    if isinstance(sub_expr.first, target_class):
                        reduction(sub_expr.first, target_class)
                    else:
                        elements.append(self.transform(sub_expr.first))
                    if isinstance(sub_expr.second, target_class):
                        reduction(sub_expr.second, target_class)
                    else:
                        elements.append(self.transform(sub_expr.second))
                reduction(expr, expr.__class__)
                def sort_method(e):
                    e_list = get_indiv_vars(e)
                    e_str = [str(obj) for obj in e_list]
                    return reduce(operator.add, e_str, "")
                elements.sort(key=sort_method)
                result = elements.pop(0)
                while len(elements):
                    result = expr.__class__(result, elements.pop(0))
                return result
            else:
                return self.recursive(expr)
        
    # inner class: dedicated checker
    class _LogicChecker(LogicChecker):
        """
        [Inner class] AST rewriter dedicated to MR-E1.4.
        Inherits the traversal from LogicChecker.
        """
        def check(self, expr: Expression) -> bool:
            """
            Rule: recursively flatten & / |.
            """
            if isinstance(expr, (AndExpression, OrExpression)):
                if isinstance(expr.first, expr.__class__) or isinstance(expr.second, expr.__class__):
                    return True
                else:
                    return self.recursive(expr.first) | self.recursive(expr.second)
            else:
                return self.recursive(expr)

    # =========================================================================
    # standard MR interface implementation
    # =========================================================================
    def source_templates(self) -> list[str]:
        return [ "c ∨ (b ∨ a)", "a ∧ (b ∧ a)", "c ∨ ((b ∧ d) ∨ a)", "c ∨ ((d ∧ b) ∨ a)"]


if __name__ == "__main__":
    # instantiate the MR to test
    mr = MRE14()
    
    # run the check
    mr.sanity_check()
