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

    # 内部类：专属 Transformer
    class _Transformer(LogicTransformer):
        """
        [Inner Class] 专门为 MR-E1.2 服务的 AST 重写器。
        继承自 utils.logic_visitor.LogicTransformer，复用其遍历能力。
        """
        def transform(self, expr: Expression) -> Expression:
            """
            规则: 先提取非~，然后看非后面的表达式
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
            
    # 内部类：专属 Checker
    class _LogicChecker(LogicChecker):
        """
        [Inner Class] 专门为 MR-E1.2 服务的 AST 重写器。
        继承自 equivalence_utils.LogicChecker，复用其遍历能力。
        """
        def check(self, expr: Expression) -> bool:
            """
            规则: 先提取非~，然后看非后面的表达式
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
    # MR 标准接口实现
    # =========================================================================
    def source_templates(self) -> list[str]:
        return ["--A", "-( A & B )", "-( A | B )", "-all x.A", "-exists x.A"]


if __name__ == "__main__":
    # 实例化你要测的 MR
    mr = MRE12()
    
    # 准备几个经典的逻辑公式（包含 Unicode）
    test_cases = [
        "¬(p ∧ q)",
        "¬¬(p ∧ q)",
        "-all x.A"
    ]