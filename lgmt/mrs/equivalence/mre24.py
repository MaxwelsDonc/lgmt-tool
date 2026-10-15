"""
MR-E2.4: Distributivity Law
"""
import sys
import os


from functools import reduce
from lgmt.core.structure import TestCase
from nltk.sem.logic import (
    Expression, 
    AndExpression, 
    OrExpression, 
    LogicParser,
)
from lgmt.mrs.equivalence.equivalence_utils import MetamorphicTransform, LogicTransformer, LogicChecker

# =============================================================================
# MR-E2.4: Distributivity Law
# =============================================================================

class MRE24(MetamorphicTransform):
    """Distributivity Law (MR-E2.4)."""

    def __init__(self):
        super().__init__(
            index="MR-E2.4", 
            name="Distributivity Law",
            transformer=self._Transformer(),
            logic_checker=self._LogicChecker()
        )

    # inner class: dedicated transformer
    class _Transformer(LogicTransformer):
        """
        [Inner class] AST rewriter dedicated to MR-E2.4 (optimized).
        """
        def __init__(self):
            self.targets = [AndExpression, OrExpression]

        def transform(self, expr: Expression) -> Expression:
            if isinstance(expr, (AndExpression, OrExpression)):
                # 1. identify the current operator (AND or OR)
                target_class = expr.__class__
                if isinstance(expr, AndExpression):
                    target_id = 0 # Current is AND
                else:
                    target_id = 1 # Current is OR
                
                # 2. iterate with an explicit stack instead of recursive reduction
                # avoids RecursionError on deeply nested formulas
                elements = []
                stack = [expr]
                
                while stack:
                    curr = stack.pop()
                    if isinstance(curr, target_class):
                        # keep left-to-right order: push right first, then left
                        stack.append(curr.second)
                        stack.append(curr.first)
                    else:
                        # rewrite children only; this level's logic is untouched
                        elements.append(self.transform(curr))
                
                # 3. complexity guard
                # distributing a level with >20 elements would blow up; keep the flat form
                if len(elements) > 20:
                    return reduce(target_class, elements)

                # 4. look for a distribution opportunity (e.g. an OR inside an AND level)
                other_expr_id = None
                search_target_type = self.targets[not target_id]

                for k in range(len(elements)):
                    if isinstance(elements[k], search_target_type):
                        other_expr_id = k
                        break
                
                if other_expr_id is not None:
                    # found one: distribute
                    other_expr = elements.pop(other_expr_id)  # take out the (B | C)
                    
                    # the rest recombines into A
                    if elements:
                        rest_expr = reduce(target_class, elements)
                    else:
                        return other_expr 

                    # build the new formula
                    # e.g. A & (B | C) -> (A & B) | (A & C)
                    new_op_class = self.targets[not target_id]  # outer becomes OR
                    inner_op_class = self.targets[target_id]  # inner becomes AND

                    # no recursive self.transform call here
                    # old code recursed here and could loop forever
                    # new code returns the single-step result
                    left_part = inner_op_class(rest_expr, other_expr.first)
                    right_part = inner_op_class(rest_expr, other_expr.second)
                    
                    return new_op_class(left_part, right_part)

                else:
                    # no opportunity: return the flattened recombination
                    return reduce(target_class, elements)
            else:
                # generic recursion for other nodes
                return self.recursive(expr)
        
    class _LogicChecker(LogicChecker):
        """
        [Inner class] Checker dedicated to MR-E2.4 (optimized).
        """
        def __init__(self):
            self.targets = [AndExpression, OrExpression]

        def check(self, expr: Expression) -> bool:
            if isinstance(expr, (AndExpression, OrExpression)):
                if isinstance(expr, AndExpression):
                    target_id = 0
                else:
                    target_id = 1
                
                # iterative stack-based check
                stack = [expr]
                target_class = expr.__class__
                opposite_class = self.targets[not target_id]

                while stack:
                    curr = stack.pop()
                    if isinstance(curr, target_class):
                        stack.append(curr.second)
                        stack.append(curr.first)
                    elif isinstance(curr, opposite_class):
                        # target found: an OR inside an AND chain
                        return True
                    else:
                        # check children for deeper opportunities
                        if self.recursive(curr):
                            return True
                return False
            else:
                return self.recursive(expr)

    # =========================================================================
    # standard MR interface implementation
    # =========================================================================
    def source_templates(self) -> list[str]:
        return [ "a & (b | c)", "a | (b & c) | d", "a | (b & c) | (d & e)"]
