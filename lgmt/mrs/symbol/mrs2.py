"""
MRS2: Predicate Renaming Invariance
"""
import copy
import sys
import os


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
# MR-S2: Predicate Renaming Invariance
# =============================================================================
class MRS2(MetamorphicRelation):
    def __init__(self):
        self.index="MR-S2"
        self.name="Predicate Renaming Invariance"

    def _extract_predicates(self, expr):
        """Recursively collect all predicate symbols."""
        from nltk.sem.logic import ApplicationExpression, BinaryExpression, NegatedExpression, VariableBinderExpression
        predicates = set()
        
        if isinstance(expr, ApplicationExpression):
            func = expr.function
            while isinstance(func, ApplicationExpression):
                func = func.function
            pred_name = str(func)
            predicates.add(pred_name)
            predicates.update(self._extract_predicates(expr.argument))
        elif isinstance(expr, BinaryExpression):
            predicates.update(self._extract_predicates(expr.first))
            predicates.update(self._extract_predicates(expr.second))
        elif isinstance(expr, NegatedExpression):
            predicates.update(self._extract_predicates(expr.term))
        elif isinstance(expr, VariableBinderExpression):
            predicates.update(self._extract_predicates(expr.term))
        
        return predicates
    
    class _PredicateRenamer():
        """
        [Inner class] AST rewriter dedicated to MR-S2.
        Substitute predicate symbols.
        """
        def __init__(self, predicate_mapping=None):
            self.predicate_mapping = predicate_mapping if predicate_mapping else {}
        
        def transform(self, expr):
            """Walk the AST and substitute predicates."""
            if isinstance(expr, ApplicationExpression):
                # predicate application, e.g. Man(socrates)
                func = expr.function
                arg = expr.argument
                pred_name = str(func)

                if pred_name in self.predicate_mapping:
                    new_func = func.__class__.fromstring(self.predicate_mapping[pred_name])
                    new_arg = self.transform(arg)
                    return ApplicationExpression(new_func, new_arg)
                else:
                    return self.recursive(expr)
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
        Check whether any predicate can be renamed.
        """
        try:
            expr = LogicParser().parse(fol)
            predicates = self._extract_predicates(expr)
            return len(predicates) > 0
        except:
            return False   
    def source_templates(self) -> List[str]:
        return ["P(a)", "R(x,c)", "all x.(P(x) -> Q(a))", "Mortal(socrates)", "exists y.Loves(john,y)"]

    def check_applicability(self, test_case: TestCase) -> bool:
        """Check whether MRS2 applies to the data."""
        premises_logic : List[str] = test_case.premises_logic
        return any(self.check_applicability_logic(s) for s in premises_logic)

    def transform(self, source_TC: TestCase, new_pred_list=None) -> TestCase:
        """
        (Γ, q) => (Γ', q'): all predicates are renamed uniformly.
        """
        if new_pred_list is None:
            new_pred_list = ['Pre1', 'Pre2', 'Pre3', 'Pre4', 'Pre5', 'Pre6', 'Pre7', 'Pre8', 'Pre9', 'Pre10']

        follow_TC = copy.deepcopy(source_TC)
        parser = LogicParser()

        # collect the predicates
        all_predicates = set()
        for formula in source_TC.premises_logic + [source_TC.conclusion_logic]:
            try:
                expr = parser.parse(formula)
                predicates = self._extract_predicates(expr)
                all_predicates.update(predicates)
            except:
                pass  
        
        # build the mapping
        pred_mapping = {}
        sorted_predicates = sorted(list(all_predicates)) 
        for i, pred in enumerate(sorted_predicates):
            if i < len(new_pred_list):
                pred_mapping[pred] = new_pred_list[i]
            else:
                pred_mapping[pred] = f'Pred{i}'
        
        
        transformer = self._PredicateRenamer(pred_mapping)
        
        # rename premises
        # step 4: rename premises
        new_premises_logic = []
        new_premises_text = []
        for idx, (p_logic, p_text) in enumerate(zip(source_TC.premises_logic, source_TC.premises_text)):
            try:
                expr = parser.parse(p_logic)
                preds = self._extract_predicates(expr)
                if len(preds) > 0:
                    new_expr = transformer.transform(expr)
                    new_premises_logic.append(str(new_expr))
                    new_premises_text.append(f"[Changed_{idx}] {p_text}")
                else:
                    new_premises_logic.append(p_logic)
                    new_premises_text.append(p_text)
            except Exception as e:
                new_premises_logic.append(p_logic)
                new_premises_text.append(p_text)

        
        # rename the conclusion
        try:
            expr = parser.parse(source_TC.conclusion_logic)
            if len(self._extract_predicates(expr)) > 0:
                new_expr = transformer.transform(expr)
                new_conclusion_logic = str(new_expr)
                new_conclusion_text = f"[Changed_conclusion] {source_TC.conclusion_text}"
            else:
                new_conclusion_logic = source_TC.conclusion_logic
                new_conclusion_text = source_TC.conclusion_text
        except Exception as e:
            new_conclusion_logic = source_TC.conclusion_logic
            new_conclusion_text

        follow_TC.premises_logic = new_premises_logic
        follow_TC.premises_text = new_premises_text 
        follow_TC.conclusion_logic = new_conclusion_logic
        follow_TC.conclusion_text = new_conclusion_text
        follow_TC.metadata['mapping'] = pred_mapping

       
        return follow_TC
