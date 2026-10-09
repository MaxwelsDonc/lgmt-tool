"""
MR-E1.5: Alpha-Renaming (Stream-based Implementation)
"""
import operator
from functools import reduce
import sys
import os

# path adaptation

# 1. NLTK core imports
from nltk.sem.logic import (
    Expression, 
    BinaryExpression, 
    IndividualVariableExpression, 
    Variable,
    QuantifiedExpression,
    ApplicationExpression,
    FunctionVariableExpression,
    LambdaExpression,
    ConstantExpression,
    NegatedExpression,
    EqualityExpression
)

# 2. custom base classes
from lgmt.mrs.equivalence.equivalence_utils import MetamorphicTransform, LogicTransformer, LogicChecker

from lgmt.core.structure import TestCase

# =============================================================================
# helper: global scan (used to generate fresh names)
# =============================================================================
def get_vars_final(e) -> list:
    """Collect all variables and constants for the reserved-name set."""
    if isinstance(e, (QuantifiedExpression, LambdaExpression)):
        return [(e.variable, 'Binder')] + get_vars_final(e.term)
    elif isinstance(e, FunctionVariableExpression):
        return []
    elif isinstance(e, IndividualVariableExpression):
        return [(e.variable, 'Argument')] 
    elif isinstance(e, ConstantExpression):
        return [(e.variable, 'Argument')]
    else:
        # recurse for Application/Binary nodes
        return e.visit(get_vars_final, lambda parts: reduce(operator.add, parts, []))

# =============================================================================
# main class
# =============================================================================
class MRE15(MetamorphicTransform):
    def __init__(self):
        super().__init__(
            index="MR-E1.5", 
            name="Alpha-Renaming",
            transformer=self._Transformer(),
            logic_checker=self._LogicChecker()
        )

    class _Transformer(LogicTransformer):
        """
        [Scope-aware Transformer]
        Strategy:
        1. Collect the free variables of the whole expression; binders must never reuse them.
        2. Keep a forbidden_names set initialized with all free variables.
        3. For every binder x encountered:
           - if x is in forbidden_names:
             - alpha-convert x to a fresh name z.
             - Alpha-convert x -> z。
             - add z to forbidden_names.
           - otherwise:
             - add x to forbidden_names (prevents shadowing/conflicts later).
        """
        def __init__(self, original_expr: Expression = None):
            self.index = 1
            self._global_reserved = set()
            self.forbidden_names = set()
            
            if original_expr:
                self._scan_reserved(original_expr)

        def _scan_reserved(self, expr):
            """Pre-scan: record all original names so fresh names never clash."""
            all_vars = get_vars_final(expr)
            self._global_reserved.update({var.name for var, role in all_vars})

        def _get_new_var(self) -> Variable:
            """Generate a globally fresh variable name (bv1, bv2...)."""
            while True:
                name = f'bv{self.index}'
                # fresh means: not originally present and not forbidden
                if name not in self._global_reserved and name not in self.forbidden_names:
                    self._global_reserved.add(name)
                    return Variable(name)
                self.index += 1

        def transform(self, expr: Expression) -> Expression:
            """Entry point."""
            # 1. build the reserved-name set on first use
            if not self._global_reserved:
                self._scan_reserved(expr)
            
            # 2. forbid all free variables
            # free() returns a set of Variables
            self.forbidden_names = {v.name for v in expr.free()}
            
            # 3. walk the tree
            return self.visit(expr)

        def visit(self, expr):
            """
            Core dispatcher.
            """
            method_name = f"visit_{expr.__class__.__name__}"
            if hasattr(self, method_name):
                return getattr(self, method_name)(expr)
            
            # generic fallback
            return expr.visit(self.visit, lambda parts: expr.__class__(*parts))

        def visit_QuantifiedExpression(self, expr):
            var_name = expr.variable.name
            
            # conflict if the name is forbidden (free or taken by an earlier binder)
            if var_name in self.forbidden_names:
                new_var = self._get_new_var()
                # Alpha-convert
                expr = expr.alpha_convert(new_var)
                # mark the fresh name as used
                self.forbidden_names.add(new_var.name)
            else:
                # mark the name as used
                self.forbidden_names.add(var_name)
            
            # recurse into the body
            new_term = self.visit(expr.term)
            
            return expr.__class__(expr.variable, new_term)

        def visit_ExistsExpression(self, expr):
            return self.visit_QuantifiedExpression(expr)

        def visit_AllExpression(self, expr):
            return self.visit_QuantifiedExpression(expr)


        def visit_LambdaExpression(self, expr):
            # lambdas are handled like quantifiers
            return self.visit_QuantifiedExpression(expr)

        def visit_IndividualVariableExpression(self, expr):
            return expr

        def visit_ConstantExpression(self, expr):
            return expr

        def visit_FunctionVariableExpression(self, expr):
            return expr
            
        def visit_AbstractVariableExpression(self, expr):
            return expr


        # support for concrete Binary types (the fallback above also covers them)
        # only requires the Binary constructors to exist

    class _LogicChecker(LogicChecker):
        """Applicability checker (same logic as before)."""
        def check(self, expr: Expression) -> bool:
            ordered_vars = get_vars_final(expr)
            seen = set()
            for var_obj, role in ordered_vars:
                name = var_obj.name
                if role == 'Argument':
                    seen.add(name)
                elif role == 'Binder':
                    if name in seen:
                        return True
            return False

    def source_templates(self) -> list[str]:
        return ["all y.G(x,y) & all x.F(x)"]

# =============================================================================
# test driver
# =============================================================================
if __name__ == "__main__":
    mr = MRE15()
    test_case=TestCase(
            premises_text=['(all x. A(y)) & (exists y. B)'],
            conclusion_text='ok',
            premises_logic=['(all x. A(y)) & (exists y. B)'],
            conclusion_logic='ok',
            metadata=['']
        )
    follow_TC=mr.transform(test_case)
    print(follow_TC)
