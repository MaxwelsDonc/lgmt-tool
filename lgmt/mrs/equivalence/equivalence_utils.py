from functools import reduce
import operator
import abc
from nltk.sem.logic import (
    LogicParser,
    Expression,
    IndividualVariableExpression,
    AbstractVariableExpression,
)
from colorama import Fore, Style
import re
from lgmt.core.structure import TestCase, MetamorphicRelation


def get_indiv_vars(e: Expression) -> list:
    """
    Collect every IndividualVariableExpression in ``expr``.
    """
    if isinstance(e, IndividualVariableExpression):
        return [e]
    elif isinstance(e, AbstractVariableExpression):
        return []
    else:
        return e.visit(get_indiv_vars, lambda parts: reduce(operator.add, parts, []))


class LogicTransformer(abc.ABC):
    """
    Base class for recursive AST rewriting (visitor pattern).
    Walks the NLTK logic-expression tree and lets subclasses rewrite nodes.
    """

    @abc.abstractmethod
    def transform(self, expr: Expression) -> Expression:
        """
        Rewrite ``expr``.
        """
        return expr

    def recursive(self, expr: Expression) -> Expression:
        """Generic dispatch."""
        if isinstance(expr, AbstractVariableExpression):
            return expr
        else:
            return expr.visit_structured(self.transform, expr.__class__)


class LogicChecker(abc.ABC):
    """
    [Inner class] Checks whether the target pattern exists.
    """

    @abc.abstractmethod
    def check(self, expr: Expression) -> Expression:
        """
        Check whether ``expr`` satisfies the MR applicability condition.
        """
        raise NotImplementedError("define your check function")

    def recursive(self, expr: Expression) -> Expression:
        """Generic dispatch."""
        if isinstance(expr, AbstractVariableExpression):
            return False
        else:
            return expr.visit(self.check, lambda parts: reduce(operator.or_, parts))


class MetamorphicTransform(MetamorphicRelation):
    def __init__(
        self, index, name, transformer: LogicTransformer, logic_checker: LogicChecker
    ):
        # super().__init__(index, name)
        self.index = index
        self.name = name
        self.parser = LogicParser()
        self.transformer = transformer
        self.logic_checker = logic_checker

    def check_applicability_logic(self, formula: str) -> bool:
        expr = self.parser.parse(formula)
        return self.logic_checker.check(expr)

    def check_applicability(self, test_case: TestCase) -> bool:
        for f in test_case.premises_logic:
            if self.check_applicability_logic(f):
                return True
        return False

    def transform(self, stc: TestCase) -> TestCase:
        # premises
        new_premises_formulas = []
        new_premises_text = []
        for index, premises_formula_str in enumerate(stc.premises_logic):
            if not self.check_applicability_logic(premises_formula_str):
                new_premises_formulas.append(premises_formula_str)
                new_premises_text.append(stc.premises_text[index])
                continue

            # 2. Parse (Str -> AST)
            ast = self.parser.parse(premises_formula_str)
            # 3. transform (AST -> AST)
            new_ast = self.transformer.transform(ast)
            # 4. Stringify (AST -> ASCII Str)
            new_ascii_str = str(new_ast)

            new_premises_formulas.append(new_ascii_str)
            if str(new_ast) != str(ast):  # formula content changed
                new_premises_text.append(
                    f"[Changed_{index}] {stc.premises_text[index]}"
                )
            else:
                new_premises_text.append(stc.premises_text[index])

        # conclusion
        if self.check_applicability_logic(stc.conclusion_logic):
            # 2. Parse (Str -> AST)
            ast = self.parser.parse(stc.conclusion_logic)
            # 3. transform (AST -> AST)
            new_ast = self.transformer.transform(ast)
            # 4. Stringify (AST -> ASCII Str)
            new_ascii_str = str(new_ast)
            # 5. Denormalize (ASCII -> Unicode)
            new_conclusion_logic = new_ascii_str
            if new_ast != ast:  # formula content changed
                new_conclusion_text = f"[Changed_conclusion] {stc.conclusion_text}"
            elif (
                new_ascii_str != stc.conclusion_logic
            ):  # same formula, different surface string
                try:
                    if self.parser.parse(new_ascii_str[1:-1]) == ast:
                        new_conclusion_text = stc.conclusion_text
                    else:
                        new_conclusion_text = (
                            f"[Changed_conclusion] {stc.conclusion_text}"
                        )
                except Exception:
                    new_conclusion_text = f"[Changed_conclusion] {stc.conclusion_text}"
            else:
                new_conclusion_text = stc.conclusion_text
        else:
            new_conclusion_logic = stc.conclusion_logic
            new_conclusion_text = stc.conclusion_text
        return TestCase(
            premises_text=new_premises_text,
            conclusion_text=new_conclusion_text,
            premises_logic=new_premises_formulas,
            conclusion_logic=new_conclusion_logic,
        )
