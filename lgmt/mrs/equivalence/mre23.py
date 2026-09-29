"""
MR-E2.3: Identity and Domination Laws
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
# MR-E2.3: Identity and Domination Laws
# =============================================================================

class MRE23(MetamorphicTransform):
    def __init__(self):
        super().__init__(
            index="MR-E2.3", 
            name="Identity and Domination Laws",
            transformer=self._Transformer(),
            logic_checker=self._LogicChecker()
        )

    # 内部类：专属 Transformer
    class _Transformer(LogicTransformer):
        """
        [Inner Class] 专门为 MR-E1.4 服务的 AST 重写器。
        继承自 metamorphic_relations.mr_equivalence.equivalence_utils.LogicTransformer，复用其遍历能力。
        """
        def transform(self, expr: Expression) -> Expression:
            """
            规则: 递归提取且或，按字符串排序
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
                e0 = Expression.fromstring('0')
                e1 = Expression.fromstring('1')
                if isinstance(expr, AndExpression):
                    if e0 in elements:
                        return e0
                    while e1 in elements:
                        elements.remove(e1)
                elif isinstance(expr, OrExpression):
                    if e1 in elements:
                        return e1
                    while e0 in elements:
                        elements.remove(e0)
                result = elements.pop(0)
                while len(elements):
                    result = expr.__class__(result, elements.pop(0))
                return result
            else:
                return self.recursive(expr)
        
    # 内部类：专属 Checker
    class _LogicChecker(LogicChecker):
        """
        [Inner Class] 专门为 MR-E1.4 服务的 AST 重写器。
        继承自 equivalence_utils.LogicChecker，复用其遍历能力。
        """
        def check(self, expr: Expression) -> bool:
            """
            规则: 递归提取且或
            """
            if isinstance(expr, (AndExpression, OrExpression)):
                e0 = Expression.fromstring('0')
                e1 = Expression.fromstring('1')
                if expr.first in [e0, e1] or expr.second in [e0, e1]:
                    return True
                else:
                    return self.check(expr.first) | self.check(expr.second)
            else:
                return self.recursive(expr)

    # =========================================================================
    # MR 标准接口实现
    # =========================================================================
    def source_templates(self) -> list[str]:
        return [ "c ∨ (b ∨ 1)", "a ∧ (1 ∧ a)", "c ∨ ((b ∧ 0) ∨ a)", "c ∨ ((1 ∧ d) ∨ a)"]


if __name__ == "__main__":
    # 实例化你要测的 MR
    mr = MRE23()
    
    # 运行检查
    mr.sanity_check()