"""
MR-E2.1: Redundancy Elimination
"""
from functools import reduce
from operator import add
from nltk.sem.logic import (
    Expression, 
    AndExpression,
    OrExpression
)
from lgmt.mrs.equivalence.equivalence_utils import MetamorphicTransform, LogicTransformer

# =============================================================================
# MR-E2.1: Redundancy Elimination
# =============================================================================


class GlobalSimplifyFlag:
    flag = None

    @classmethod
    def set_true(cls):
        cls.flag = True

    @classmethod
    def set_false(cls):
        cls.flag = False


class SubElements:
    def __init__(self):
        self.targets = [AndExpression, OrExpression]
        self.target_id = None

    def get_sub_elements(self, e: Expression):
        if isinstance(e, self.targets[self.target_id]):
            return e.visit(self.get_sub_elements, lambda parts: reduce(add, parts))
        elif isinstance(e, self.targets[not self.target_id]):
            self.target_id = not self.target_id
            result = self.get_sub_elements(e)
            self.target_id = not self.target_id
            return [result]
        else:
            return [e]


def simplify(elements: list) -> list:
    # assumes elements are ordered
    single_element = []
    list_element = []
    for k in range(len(elements)):
        if isinstance(elements[k], list):
            elements[k] = simplify(elements[k])
            if len(elements[k]) > 1:
                list_element.append(elements[k])
                continue
            else:
                elements[k] = elements[k][0]
        single_element.append(elements[k])
    new_single_element = list(dict.fromkeys(single_element))  # deduplicate
    if len(new_single_element) < len(single_element):
        GlobalSimplifyFlag.set_true()
    list_element.sort(key=lambda x: len(x))
    new_elements = new_single_element + list_element
    delete_id = []
    for i in range(len(new_elements) - 1):
        if i in delete_id:
            continue
        for j in range(i+1, len(new_elements)):
            if j in delete_id:
                continue
            if isinstance(new_elements[i], list):
                delete = True
                for k in range(len(new_elements[i])):
                    if new_elements[i][k] != new_elements[j][k]:
                        delete = False
                        break
                if delete:
                    delete_id.append(j)
            elif isinstance(new_elements[j], list):
                if new_elements[i] in new_elements[j]:
                    delete_id.append(j)
            elif new_elements[i] == new_elements[j]:
                delete_id.append(j)
    if len(delete_id):
        GlobalSimplifyFlag.set_true()
        delete_id.sort(reverse=True)
    for k in delete_id:
        new_elements.pop(k)
    return new_elements


class MRE21(MetamorphicTransform):
    def __init__(self):
        transform_check = MRE21.UtilClass()
        super().__init__(
            index="MR-E2.1", 
            name="Redundancy Elimination",
            transformer=transform_check,
            logic_checker=transform_check
        )

    class UtilClass:
        def __init__(self):
            self.expr = None
            self.transform_result = None
            self.check_result = None
            self.util_transformer = MRE21.UtilClass._Transformer()

        # inner class: dedicated transformer
        class _Transformer(LogicTransformer):
            """
            [Inner class] AST rewriter dedicated to MR-E2.1.
            Inherits the traversal from LogicTransformer.
            The expression must be sorted before calling this.
            """
            def __init__(self):
                self.sub_elements_operator = SubElements()

            def transform(self, expr: Expression) -> Expression:
                if isinstance(expr, (AndExpression, OrExpression)):
                    if isinstance(expr, AndExpression):
                        self.sub_elements_operator.target_id = 0
                    elif isinstance(expr, OrExpression):
                        self.sub_elements_operator.target_id = 1
                    else:
                        raise TypeError("Expression is not AndExpression or OrExpression")
                    elements = self.sub_elements_operator.get_sub_elements(expr)
                    GlobalSimplifyFlag.set_false()
                    new_elements = simplify(elements)
                    if GlobalSimplifyFlag.flag:
                        new_expr = self.combine(new_elements, self.sub_elements_operator.target_id)
                        return self.recursive(new_expr)
                    else:
                        return self.recursive(expr)
                else:
                    return self.recursive(expr)
            
            def combine(self, elements: list, target_id: bool):
                if not isinstance(elements, list):
                    return elements
                expr = self.combine(elements[0], not target_id)
                for i in range(1, len(elements)):
                    if isinstance(elements[i], list):
                        expr = self.sub_elements_operator.targets[target_id](expr, self.combine(elements[i], not target_id))
                    else:
                        expr = self.sub_elements_operator.targets[target_id](expr, elements[i])
                return expr

        def _transform(self, expr: Expression) -> None:
            self.transform_result = self.util_transformer.transform(expr)
            self.check_result = self.transform_result != expr
            self.expr = expr
        
        def check(self, expr: Expression) -> bool:
            if self.expr is None or self.expr != expr:
                self._transform(expr)
                return self.check_result
            else:
                return self.check_result
        
        def transform(self, expr: Expression) -> Expression:
            if self.expr is None or self.expr != expr:
                self._transform(expr)
                return self.transform_result
            else:
                return self.transform_result

    # =========================================================================
    # standard MR interface implementation
    # =========================================================================
    def source_templates(self) -> list[str]:
        return [
            "  (a&b&(c|a|b))|(c&a&(b|b))|(c&a&(b|c|b))|(c&a&(b|d))",
            "c|(a&b&(c|a|b))|(c&a&(b|b))|(c&a&(b|c|b))|(c&a&(b|d))" ,
            "a|a",
            "a&a",
            "a|(a&b)",
            "a&(a|b)",
        ]


if __name__ == "__main__":
    # instantiate the MR to test
    mr = MRE21()
    
    # run the check
    mr.sanity_check()
