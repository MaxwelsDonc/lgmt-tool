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

    # 内部类：专属 Transformer
    class _Transformer(LogicTransformer):
        """
        [Inner Class] 专门为 MR-E1.3 服务的 AST 重写器。
        继承自 utils.logic_visitor.LogicTransformer，复用其遍历能力。
        """
        def transform(self, expr: Expression) -> Expression:
            """
            规则: 先提取或且，然后看里面的表达式是否为All或者Exists
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
            
            
    # 内部类：专属 Checker
    class _LogicChecker(LogicChecker):
        """
        [Inner Class] 专门为 MR-E1.3 服务的 AST 重写器。
        继承自 equivalence_utils.LogicChecker，复用其遍历能力。
        """
        def check(self, expr: Expression) -> bool:
            """
            规则: 先提取或且，然后看里面的表达式是否为All或者Exists
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
    # MR 标准接口实现
    # =========================================================================
    def source_templates(self) -> list[str]:
        return [
            "(all x.A) & B", 
            "(all x.A(x) & B(x))",
            "A | (exists x.B)",
        ]


if __name__ == "__main__":
    # 实例化你要测的 MR
    mr = MRE13()
    
    # 运行检查
    mr.sanity_check()