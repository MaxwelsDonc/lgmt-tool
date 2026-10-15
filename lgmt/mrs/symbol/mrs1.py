"""
MRS1: Constant Renaming Invariance
"""
import copy


from typing import List, Tuple
from lgmt.core.structure import MetamorphicRelation, TestCase
from nltk.sem.logic import(
    LogicParser, 
    AbstractVariableExpression, 
    VariableBinderExpression, 
    ApplicationExpression, 
    BinaryExpression, 
    NegatedExpression
)


# =============================================================================
# MR-S1: Constant Renaming Invariance
# =============================================================================
class MRS1(MetamorphicRelation):
    """Symbol Renaming Invariance (MR-S1)."""

    def __init__(self):
        self.index = "MR-S1"
        self.name = "Symbol Renaming Invariance"

    def _extract_constants(self,expr, bound_vars=None, in_arg=False, in_app=False):
        """Recursively collect individual constants (argument positions only;
        """
        if bound_vars is None:
            bound_vars = set()

        # conventional variable names are not treated as constants
        common_vars = {'x', 'y', 'z', 'u', 'v', 'w', 't', 's'}
        constants = set()

        if isinstance(expr, VariableBinderExpression):
            # quantified expression (all x.P(x), exists y.Q(y))
            new_bound = bound_vars | {str(expr.variable)}
            constants.update(self._extract_constants(expr.term, new_bound, in_arg=False, in_app=False))

        elif isinstance(expr, ApplicationExpression):
            # application (P(a), R(x,y))
            constants.update(self._extract_constants(expr.function, bound_vars, in_arg=False, in_app=True))
            constants.update(self._extract_constants(expr.argument, bound_vars, in_arg=True, in_app=True))
        
        elif isinstance(expr, AbstractVariableExpression):
            # variable or constant
            var_name = str(expr)
            if in_arg and var_name not in bound_vars and var_name not in common_vars:
                constants.add(var_name)

        elif isinstance(expr, BinaryExpression):
            # binary expression (A & B, A | B, A -> B)
            constants.update(self._extract_constants(expr.first, bound_vars, in_arg=False, in_app=False))
            constants.update(self._extract_constants(expr.second, bound_vars, in_arg=False, in_app=False))

        elif isinstance(expr, NegatedExpression):
            # negation (-A)
            constants.update(self._extract_constants(expr.term, bound_vars, in_arg=False, in_app=False))

        return constants
    
    class _SymbolRenamer():
        """
        Substitute individual constants.
        """
        def __init__(self, const_mapping=None):
            self.const_mapping = const_mapping if const_mapping else {}
        
        def transform(self, expr):
            """Walk the AST and substitute constants."""
            if isinstance(expr, AbstractVariableExpression):
                var_name = str(expr)
                if var_name in self.const_mapping:
                    # substitute
                    return expr.__class__.fromstring(self.const_mapping[var_name])
                else:
                    return expr
            else:
                return self.recursive(expr)
        
        def recursive(self, expr):
            """Recursively handle every expression type."""
            if isinstance(expr, VariableBinderExpression):
                # quantified expression
                return expr.__class__(expr.variable, self.transform(expr.term))
            
            elif isinstance(expr, ApplicationExpression):
                # application
                return ApplicationExpression(self.transform(expr.function), self.transform(expr.argument))
            
            elif isinstance(expr, BinaryExpression):
                # binary expression
                return expr.__class__(self.transform(expr.first), self.transform(expr.second))
            
            elif isinstance(expr, NegatedExpression):
                # negation
                return NegatedExpression(self.transform(expr.term))
            
            else:
                # anything else passes through
                return expr
    
    # =========================================================================
    # standard MR interface implementation
    # =========================================================================
    def check_applicability_logic(self, fol: str) -> bool:
        """
        Check whether any constant can be renamed.
        """
        try:
            expr = LogicParser().parse(fol)
            constants = self._extract_constants(expr)
            return len(constants) > 0
        except:
            return False   
    def source_templates(self) -> List[str]:
        return ["P(a)", "R(x,c)", "all x.(P(x) -> Q(a))", "Mortal(socrates)", "exists y.Loves(john,y)"]

    def check_applicability(self, test_case: TestCase) -> bool:
        """Check whether MRS1 applies to the data."""
        premises_logic : List[str] = test_case.premises_logic
        return any(self.check_applicability_logic(s) for s in premises_logic)
    
    def transform(self, source_TC: TestCase, new_const_list=None) -> TestCase:
        """
        (Γ, q) => (Γ', q'): all constants are renamed uniformly.
        Replace every individual constant in premises and conclusion.
        """
        if new_const_list is None:
            new_const_list = ['Con1', 'Con2', 'Con3', 'Con4', 'Con5', 'Con6', 'Con7', 'Con8', 'Con9', 'Con10']
        
        follow_TC = copy.deepcopy(source_TC)
        parser = LogicParser()
        
        # step 1: collect all constants
        all_constants = set()
        for formula in source_TC.premises_logic + [source_TC.conclusion_logic]:
            try:
                expr = parser.parse(formula)
                constants = self._extract_constants(expr)
                all_constants.update(constants)
            except Exception as e:
                pass
        
        # step 2: build the constant mapping
        const_mapping = {}
        sorted_constants = sorted(list(all_constants))
        for i, const in enumerate(sorted_constants):
            if i < len(new_const_list):
                const_mapping[const] = new_const_list[i]
            else:
                const_mapping[const] = f'Con{i+1}'
        
        # step 3: create the renamer
        transformer = self._SymbolRenamer(const_mapping)
        
        # step 4: rename premises
        new_premises_logic = []
        new_premises_text = []
        for idx, (p_logic, p_text) in enumerate(zip(source_TC.premises_logic, source_TC.premises_text)):
            try:
                expr = parser.parse(p_logic)
                consts = self._extract_constants(expr)
                if consts:
                    new_expr = transformer.transform(expr)
                    new_premises_logic.append(str(new_expr))
                    new_premises_text.append(f"[Changed_{idx}] {p_text}")
                else:
                    new_premises_logic.append(p_logic)
                    new_premises_text.append(p_text)
            except Exception:
                new_premises_logic.append(p_logic)
                new_premises_text.append(p_text)

        # step 5: rename the conclusion
        try:
            expr = parser.parse(source_TC.conclusion_logic)
            if self._extract_constants(expr):
                new_conclusion = str(transformer.transform(expr))
                new_conclusion_text = f"[Changed_conclusion] {source_TC.conclusion_text}"
            else:
                new_conclusion = source_TC.conclusion_logic
                new_conclusion_text = source_TC.conclusion_text
        except Exception:
            new_conclusion = source_TC.conclusion_logic
            new_conclusion_text = source_TC.conclusion_text

        # step 6: update the follow-up test case
        follow_TC.premises_logic = new_premises_logic
        follow_TC.premises_text = new_premises_text
        follow_TC.conclusion_logic = new_conclusion
        follow_TC.conclusion_text = new_conclusion_text
        follow_TC.metadata["mapping"] = const_mapping

        return follow_TC
