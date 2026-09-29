"""
MR-E1.6: Canonical Quantifier Ordering
"""
from typing import List, Tuple
from nltk.sem.logic import (
    Expression, 
    ExistsExpression,
    AllExpression,
    IndividualVariableExpression
)
from lgmt.mrs.equivalence.equivalence_utils import MetamorphicTransform, LogicTransformer, LogicChecker, get_indiv_vars

AllExistsExpressionTuple = (AllExpression, ExistsExpression)

# =============================================================================
# MR-E1.6: Canonical Quantifier Ordering
# =============================================================================

class MRE16(MetamorphicTransform):
    def __init__(self):
        super().__init__(
            index="MR-E1.6", 
            name="Canonical Quantifier Ordering",
            transformer=self._Transformer(),
            logic_checker=self._LogicChecker()
        )

    # 内部类：专属 Transformer
    class _Transformer(LogicTransformer):
        """
        [Inner Class] 专门为 MR-E1.6 服务的 AST 重写器。
        继承自 utils.logic_visitor.LogicTransformer，复用其遍历能力。
        """
        def transform(self, expr: Expression) -> Expression:
            if isinstance(expr, AllExistsExpressionTuple):
                elements = []
                final_expr = expr
                while isinstance(final_expr, expr.__class__):
                    elements.append([expr.__class__, final_expr.variable])
                    final_expr = final_expr.term
                variables = get_indiv_vars(final_expr)
                for e in elements:
                    if IndividualVariableExpression(e[1]) in variables:
                        e.append(variables.index(IndividualVariableExpression(e[1])))
                    else:
                        e.append(len(variables))
                elements.sort(key = lambda x: (x[2], x[1]))
                final_expr = self.transform(final_expr)
                while len(elements):
                    TargetClass, variable, _ = elements.pop()
                    final_expr = TargetClass(variable, final_expr)
                return final_expr
            else:
                return self.recursive(expr)
        
    # 内部类：专属 Checker
    class _LogicChecker(LogicChecker):
        """
        [Inner Class] 专门为 MR-E1.6 服务的 AST 重写器。
        继承自 equivalence_utils.LogicChecker，复用其遍历能力。
        """
        def check(self, expr: Expression) -> bool:
            if isinstance(expr, AllExistsExpressionTuple):
                if isinstance(expr.term, AllExistsExpressionTuple):
                    return True
                else:
                    return self.recursive(expr.term)
            else:
                return self.recursive(expr)

    # =========================================================================
    # MR 标准接口实现
    # =========================================================================
    def source_templates(self) -> list[str]:
        return [ "all x.(exists w.(exists y. all d. all c. all b. exist z. exist r. D(z,y,x)))"]


if __name__ == "__main__":
    # 实例化你要测的 MR
    mr = MRE16()
    
    # 运行检查
    mr.sanity_check()